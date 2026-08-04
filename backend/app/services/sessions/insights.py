from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.text_sanitizer import clean_captured_text, clean_graph_docs
from .workflow import build_markdown_workflow_runs


PHASE_LABELS: dict[str, str] = {
    "implementation": "구현",
    "review": "리뷰",
    "review_fix": "리뷰 반영",
    "verification": "검증",
    "planning": "정리",
}
DIFF_STEP_KINDS = {"implementation", "review_fix"}


def enrich_session_response(response: dict[str, Any]) -> dict[str, Any]:
    """Attach deterministic session/group summaries to a session payload."""
    enriched = deepcopy(response)
    groups = [
        enrich_group(group, index + 1)
        for index, group in enumerate(enriched.get("groups") or [])
        if isinstance(group, dict)
    ]
    enriched["groups"] = groups
    enriched["summary"] = build_session_summary(groups)
    return enriched


def enrich_group(group: dict[str, Any], sequence: int) -> dict[str, Any]:
    enriched = deepcopy(group)
    graph = _graph(enriched)
    prompt = str(enriched.get("user_prompt") or "")
    response = clean_captured_text(
        str(enriched.get("assistant_response") or graph.get("assistant_response") or "")
    )
    enriched["assistant_response"] = response
    if graph:
        enriched["graph"] = clean_graph_docs(graph)
        graph = _graph(enriched)
    explicit_workflow_runs = _clean_workflow_runs(enriched.get("workflow_runs"))
    workflow_graph = _combined_workflow_graph(explicit_workflow_runs)
    if explicit_workflow_runs:
        graph = clean_graph_docs(workflow_graph)
        enriched["graph"] = graph
    file_nodes = _changed_file_nodes(graph)
    phase = _explicit_workflow_phase(explicit_workflow_runs) or infer_phase(prompt, response, file_nodes)

    enriched["sequence"] = sequence
    enriched["phase"] = phase
    enriched["phase_label"] = PHASE_LABELS.get(phase, phase)
    workflow_runs = explicit_workflow_runs or build_markdown_workflow_runs(
        prompt=prompt,
        response=response,
        graph=graph,
    )
    enriched["workflow_runs"] = workflow_runs
    implementation_items = (
        _workflow_step_summaries(explicit_workflow_runs, {"implementation", "review_fix"})
        if explicit_workflow_runs
        else implementation_summary(file_nodes, response)
    )
    review_items = (
        _workflow_step_summaries(explicit_workflow_runs, {"review", "verification"})
        if explicit_workflow_runs
        else review_summary(prompt, response, phase)
    )
    enriched["summary"] = {
        "implementation": implementation_items,
        "review": review_items,
        "technical_considerations": technical_considerations(graph, prompt, response),
        "changed_files": [node.get("file", "") for node in file_nodes if node.get("file")],
        "file_count": len(file_nodes),
        "edge_count": len(graph.get("edges") or []),
        "added_lines": _sum_node_int(file_nodes, "added_lines"),
        "removed_lines": _sum_node_int(file_nodes, "removed_lines"),
        "workflow_run_count": len(workflow_runs),
        "workflow_step_count": sum(len(run.get("steps") or []) for run in workflow_runs),
    }
    return enriched


def build_session_summary(groups: list[dict[str, Any]]) -> dict[str, Any]:
    files: list[str] = []
    implementation_items: list[str] = []
    review_items: list[str] = []
    considerations: list[dict[str, str]] = []
    phase_counts: dict[str, int] = {}
    added = 0
    removed = 0
    workflow_run_count = 0
    workflow_step_count = 0

    for group in groups:
        phase = str(group.get("phase") or "implementation")
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        summary = group.get("summary") if isinstance(group.get("summary"), dict) else {}
        files.extend(str(item) for item in summary.get("changed_files") or [] if item)
        implementation_items.extend(str(item) for item in summary.get("implementation") or [] if item)
        review_items.extend(str(item) for item in summary.get("review") or [] if item)
        considerations.extend(
            item
            for item in summary.get("technical_considerations") or []
            if isinstance(item, dict) and item.get("label")
        )
        added += int(summary.get("added_lines") or 0)
        removed += int(summary.get("removed_lines") or 0)
        workflow_run_count += int(summary.get("workflow_run_count") or 0)
        workflow_step_count += int(summary.get("workflow_step_count") or 0)

    return {
        "total_groups": len(groups),
        "phase_counts": phase_counts,
        "changed_files": _unique(files)[:24],
        "implementation": _unique(implementation_items)[:8],
        "review": _unique(review_items)[:8],
        "technical_considerations": _unique_considerations(considerations)[:8],
        "added_lines": added,
        "removed_lines": removed,
        "workflow_run_count": workflow_run_count,
        "workflow_step_count": workflow_step_count,
    }


def infer_phase(prompt: str, response: str, file_nodes: list[dict[str, Any]]) -> str:
    text = f"{prompt}\n{response}".lower()
    has_changes = bool(file_nodes)
    review_signal = _contains_any(
        text,
        [
            "codex review",
            "/review",
            "review",
            "리뷰",
            "검토",
            "finding",
            "p0",
            "p1",
            "p2",
            "actionable",
        ],
    )
    fix_signal = _contains_any(text, ["address", "fixed", "반영", "수정 완료", "고쳤", "해결"])
    verification_signal = _contains_any(text, ["test", "pytest", "typecheck", "검증", "테스트"])
    planning_signal = _contains_any(text, ["plan", "계획", "설계", "정리"]) and not has_changes

    if review_signal and fix_signal and has_changes:
        return "review_fix"
    if has_changes:
        return "implementation"
    if review_signal:
        return "review"
    if verification_signal and not has_changes:
        return "verification"
    if planning_signal:
        return "planning"
    return "implementation"


def implementation_summary(file_nodes: list[dict[str, Any]], response: str) -> list[str]:
    items = _extract_response_items(
        response,
        [
            "구현",
            "수정",
            "추가",
            "변경",
            "정리",
            "전환",
            "removed",
            "implemented",
            "updated",
        ],
    )
    if items:
        return items[:5]

    if not file_nodes:
        return ["이 단계에서 새 diff 파일은 감지되지 않았습니다."]

    return [
        f"`{node.get('file')}`: {status_label(str(node.get('status') or 'modified'))}, "
        f"+{int(node.get('added_lines') or 0)}/-{int(node.get('removed_lines') or 0)}"
        for node in file_nodes[:5]
        if node.get("file")
    ]


def review_summary(prompt: str, response: str, phase: str) -> list[str]:
    items = _extract_response_items(
        f"{prompt}\n{response}",
        [
            "review",
            "리뷰",
            "검토",
            "finding",
            "actionable",
            "테스트",
            "검증",
            "issue",
            "risk",
            "위험",
        ],
    )
    if items:
        return items[:5]
    if phase == "review":
        return ["리뷰 단계로 기록됐지만 요약 가능한 지적사항 문장은 감지되지 않았습니다."]
    if phase == "review_fix":
        return ["리뷰에서 나온 수정 요청을 반영한 구현 단계입니다."]
    return []


def technical_considerations(
    graph: dict[str, Any],
    prompt: str,
    response: str,
) -> list[dict[str, str]]:
    text = f"{prompt}\n{response}\n{_files_text(graph)}".lower()
    checks: list[tuple[str, str, list[str]]] = [
        (
            "리뷰 루프",
            "구현과 리뷰 결과가 같은 세션 흐름 안에서 이어지도록 단계 정보를 유지합니다.",
            ["review", "리뷰", "검토", "finding", "actionable"],
        ),
        (
            "세션 지속성",
            "대화 thread와 project root 기준으로 group을 저장하고 다시 불러옵니다.",
            ["session", "세션", "thread", "group", "store", "capture"],
        ),
        (
            "Diff 경계",
            "누적 branch diff에서 이번 capture에 해당하는 파일만 분리해 세션 노이즈를 줄입니다.",
            ["diff", "branch", "delta", "git", "변경"],
        ),
        (
            "UI 흐름",
            "파일 단위 설명보다 구현/리뷰 단계와 최종 요약을 먼저 읽을 수 있게 화면을 구성합니다.",
            ["frontend", "react", "ui", "화면", "패널", "flow", "visual"],
        ),
        (
            "백엔드 API",
            "FastAPI 응답이 그래프와 세션 요약을 함께 제공하도록 계약을 확장합니다.",
            ["backend", "api", "fastapi", "router", "service"],
        ),
        (
            "자동화 Skill",
            "Codex/Claude skill capture가 외부 LLM 없이 로컬 backend에 세션 이벤트를 남깁니다.",
            ["skill", "codex", "claude", "capture", "automation"],
        ),
        (
            "검증",
            "작은 단위 테스트와 타입 체크로 세션 요약/렌더링 회귀를 잡는 흐름을 유지합니다.",
            ["test", "pytest", "typecheck", "검증", "테스트"],
        ),
        (
            "데이터 모델",
            "group, phase, summary, graph를 분리해 시각화와 상세 패널이 같은 사실 데이터를 공유합니다.",
            ["type", "interface", "model", "schema", "summary"],
        ),
    ]

    found: list[dict[str, str]] = []
    for label, detail, keywords in checks:
        if any(keyword in text for keyword in keywords):
            found.append({"label": label, "detail": detail})
    return found[:6]


def status_label(status: str) -> str:
    return {
        "added": "추가",
        "modified": "수정",
        "deleted": "삭제",
        "renamed": "이름 변경",
    }.get(status, status or "변경")


def _graph(group: dict[str, Any]) -> dict[str, Any]:
    graph = group.get("graph")
    return graph if isinstance(graph, dict) else {}


def _clean_workflow_runs(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    runs: list[dict[str, Any]] = []
    for run in value:
        if not isinstance(run, dict):
            continue
        steps: list[dict[str, Any]] = []
        for step in run.get("steps") or []:
            if not isinstance(step, dict):
                continue
            cleaned_step = deepcopy(step)
            step_graph = cleaned_step.get("graph")
            if isinstance(step_graph, dict):
                cleaned_step["graph"] = clean_graph_docs(step_graph)
            steps.append(cleaned_step)
        cleaned_run = deepcopy(run)
        cleaned_run["steps"] = steps
        cleaned_run["skill_label"] = _workflow_skill_label(
            str(cleaned_run.get("skill") or ""),
            str(cleaned_run.get("skill_label") or ""),
        )
        cleaned_run["command_label"] = _localized_command_label(str(cleaned_run.get("command_label") or ""))
        cleaned_run.pop("latest_full_graph", None)
        runs.append(cleaned_run)
    return runs


def _workflow_skill_label(skill: str, label: str) -> str:
    known = {
        "markdown-branch-push": "Markdown 브랜치 푸시",
        "markdown-branch-commit": "Markdown 브랜치 커밋",
        "captured-turn": "캡처된 턴",
        "codeflow": "Codeflow 작업 기록",
        "general": "일반 작업 기록",
        "Markdown Branch Push": "Markdown 브랜치 푸시",
        "Markdown Branch Commit": "Markdown 브랜치 커밋",
        "Captured turn": "캡처된 턴",
    }
    cleaned = label.strip() or skill.strip()
    return known.get(cleaned, known.get(skill.strip(), cleaned))


def _localized_command_label(label: str) -> str:
    cleaned = label.strip()
    replacements = {
        "Markdown Branch Push": "Markdown 브랜치 푸시",
        "Markdown Branch Commit": "Markdown 브랜치 커밋",
        "Captured turn": "캡처된 턴",
    }
    for source, target in replacements.items():
        cleaned = cleaned.replace(source, target)
    return cleaned


def _combined_workflow_graph(workflow_runs: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_index_by_id: dict[str, int] = {}
    edge_ids: set[str] = set()
    base: dict[str, Any] = {
        "project_root": "",
        "source": "session-events",
        "base_ref": None,
        "head_ref": None,
        "narrative": "",
        "warnings": [],
        "nodes": nodes,
        "edges": edges,
        "assistant_response": "",
    }

    for run in workflow_runs:
        for step in run.get("steps") or []:
            if not isinstance(step, dict):
                continue
            graph = step.get("graph")
            if not isinstance(graph, dict):
                continue
            for key in ["project_root", "source", "base_ref", "head_ref", "assistant_response"]:
                if graph.get(key) and not base.get(key):
                    base[key] = graph.get(key)
            if step.get("kind") not in DIFF_STEP_KINDS:
                continue
            for warning in graph.get("warnings") or []:
                if warning not in base["warnings"]:
                    base["warnings"].append(warning)
            for node in graph.get("nodes") or []:
                if not isinstance(node, dict):
                    continue
                node_id = str(node.get("id") or node.get("file") or "")
                if not node_id:
                    continue
                existing_index = node_index_by_id.get(node_id)
                if existing_index is not None:
                    nodes[existing_index] = _merge_workflow_graph_node(nodes[existing_index], node)
                    continue
                node_index_by_id[node_id] = len(nodes)
                nodes.append(node)
            for edge in graph.get("edges") or []:
                if not isinstance(edge, dict):
                    continue
                edge_id = str(edge.get("id") or f"{edge.get('source')}->{edge.get('target')}")
                if not edge_id or edge_id in edge_ids:
                    continue
                edge_ids.add(edge_id)
                edges.append(edge)
    return base


def _merge_workflow_graph_node(existing: dict[str, Any], node: dict[str, Any]) -> dict[str, Any]:
    if not _is_changed_file_node(existing) or not _is_changed_file_node(node):
        return existing

    merged = deepcopy(existing)
    merged["added_lines"] = int(existing.get("added_lines") or 0) + int(node.get("added_lines") or 0)
    merged["removed_lines"] = int(existing.get("removed_lines") or 0) + int(node.get("removed_lines") or 0)
    merged["snippet"] = _join_unique_text(
        [str(existing.get("snippet") or ""), str(node.get("snippet") or "")],
        separator="\n",
    )
    merged["body"] = _join_unique_text(
        [str(existing.get("body") or ""), str(node.get("body") or "")],
        separator="\n\n",
    )
    if not str(merged.get("summary") or "").strip():
        merged["summary"] = str(node.get("summary") or "").strip()
    return merged


def _is_changed_file_node(node: dict[str, Any]) -> bool:
    return node.get("kind") == "changed" and node.get("symbol_kind") == "file"


def _join_unique_text(values: list[str], *, separator: str) -> str:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = value.strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        output.append(cleaned)
    return separator.join(output)


def _explicit_workflow_phase(workflow_runs: list[dict[str, Any]]) -> str:
    latest_step: dict[str, Any] | None = None
    latest_key: tuple[int, str, int] = (-1, "", -1)
    for run in workflow_runs:
        for step in run.get("steps") or []:
            if not isinstance(step, dict):
                continue
            key = (
                int(step.get("event_order") or 0),
                str(step.get("created_at") or ""),
                int(step.get("sequence") or 0),
            )
            if key >= latest_key:
                latest_key = key
                latest_step = step
    kind = str(latest_step.get("kind") or "") if latest_step else ""
    if kind in {"implementation", "review", "review_fix", "verification"}:
        return kind
    if kind in {"preflight", "markdown", "branch"}:
        return "planning"
    if kind in {"commit", "push", "merge"}:
        return "verification"
    return ""


def _workflow_step_summaries(
    workflow_runs: list[dict[str, Any]],
    kinds: set[str],
) -> list[str]:
    items: list[str] = []
    for run in workflow_runs:
        for step in run.get("steps") or []:
            if not isinstance(step, dict) or step.get("kind") not in kinds:
                continue
            summary = str(step.get("summary") or "").strip()
            if summary:
                items.append(summary)
    return _unique(items)[:5]


def _changed_file_nodes(graph: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    return [
        node
        for node in nodes
        if isinstance(node, dict)
        and node.get("kind") == "changed"
        and node.get("symbol_kind") == "file"
    ]


def _sum_node_int(nodes: list[dict[str, Any]], key: str) -> int:
    return sum(int(node.get(key) or 0) for node in nodes)


def _contains_any(text: str, needles: list[str]) -> bool:
    return any(needle in text for needle in needles)


def _extract_response_items(response: str, keywords: list[str]) -> list[str]:
    items: list[str] = []
    for raw in response.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"^[-*]\s+", "", line)
        line = re.sub(r"^\d+\.\s+", "", line)
        if len(line) > 180:
            line = line[:177].rstrip() + "..."
        lower = line.lower()
        if any(keyword.lower() in lower for keyword in keywords):
            items.append(line)
    return _unique(items)


def _files_text(graph: dict[str, Any]) -> str:
    return "\n".join(
        str(node.get("file") or Path(str(node.get("label") or "")).name)
        for node in _changed_file_nodes(graph)
    )


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(normalized)
    return output


def _unique_considerations(values: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    output: list[dict[str, str]] = []
    for value in values:
        label = str(value.get("label") or "").strip()
        detail = str(value.get("detail") or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        output.append({"label": label, "detail": detail})
    return output
