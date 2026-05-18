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
    file_nodes = _changed_file_nodes(graph)
    phase = infer_phase(prompt, response, file_nodes)

    enriched["sequence"] = sequence
    enriched["phase"] = phase
    enriched["phase_label"] = PHASE_LABELS.get(phase, phase)
    workflow_runs = build_markdown_workflow_runs(
        prompt=prompt,
        response=response,
        graph=graph,
    )
    enriched["workflow_runs"] = workflow_runs
    enriched["summary"] = {
        "implementation": implementation_summary(file_nodes, response),
        "review": review_summary(prompt, response, phase),
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
        return ["리뷰 단계로 기록됐지만 요약 가능한 finding 문장은 감지되지 않았습니다."]
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
