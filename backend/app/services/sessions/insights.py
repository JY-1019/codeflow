from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from app.services.text_sanitizer import clean_captured_text, clean_graph_docs
from .workflow import build_markdown_workflow_runs


PHASE_LABELS: dict[str, str] = {
    "implementation": "Implementation",
    "review": "Review",
    "review_fix": "Review fix",
    "verification": "Verification",
    "planning": "Planning",
}
DIFF_STEP_KINDS = {"implementation", "review_fix"}
LEGACY_STEP_LABELS = {
    "preflight": ("사전 확인", "Preflight"),
    "markdown": ("Markdown 명령 해석", "Parse Markdown command"),
    "branch": ("작업 브랜치 준비", "Prepare work branch"),
    "implementation": ("구현 작업", "Implementation"),
    "review": ("리뷰 실행", "Run review"),
    "review_fix": ("리뷰 반영", "Apply review fixes"),
    "verification": ("검증", "Verification"),
    "commit": ("커밋", "Commit"),
    "push": ("브랜치 푸시", "Push branch"),
    "merge": ("main 병합/푸시", "Merge/push main"),
}
LEGACY_STEP_SUMMARIES = {
    "preflight": {
        "저장소와 리뷰 실행 조건을 확인했습니다.": "Checked the repository and review prerequisites.",
        "저장소 상태, 기준 브랜치, 리뷰 명령 가능 여부를 확인합니다.": "Checks repository status, the base branch, and review command availability.",
    },
    "markdown": {
        "Markdown 요청을 구현 단위로 기록했습니다.": "Recorded the Markdown request as an implementation unit.",
        "Markdown 파일 또는 현재 요청을 하나의 구현 단위로 읽습니다.": "Reads the Markdown file or current request as one implementation unit.",
    },
    "branch": {
        "Markdown 단위 작업 브랜치를 준비했습니다.": "Prepared a work branch for the Markdown unit.",
        "Markdown 단위별 작업 브랜치를 기준 브랜치에서 준비합니다.": "Prepares a work branch for each Markdown unit from the base branch.",
    },
    "implementation": {
        "구현 단계가 기록되었습니다.": "Recorded the implementation step.",
        "구현 작업 내용을 아직 diff에서 찾지 못했습니다.": "No implementation details have been found in the diff yet.",
    },
    "review": {
        "리뷰 결과를 기록했습니다.": "Recorded the review result.",
        "리뷰 명령을 실행해 정확성/설계 지적사항을 확인합니다.": "Runs a review command to find correctness and design issues.",
    },
    "review_fix": {
        "리뷰 반영 단계가 기록되었습니다.": "Recorded the review-fix step.",
        "리뷰 지적사항이 있으면 수정하고 다시 리뷰합니다.": "Applies review findings, then runs review again.",
    },
    "verification": {
        "검증 결과를 기록했습니다.": "Recorded the verification result.",
        "리뷰 이후 필요한 좁은 검증을 실행합니다.": "Runs focused verification after review.",
    },
    "commit": {
        "커밋 결과를 기록했습니다.": "Recorded the commit result.",
        "해당 Markdown 단위에 속한 파일만 커밋합니다.": "Commits only files belonging to the current Markdown unit.",
    },
    "push": {
        "브랜치 푸시 결과를 기록했습니다.": "Recorded the branch push result.",
        "파일 브랜치를 origin에 푸시합니다.": "Pushes the file branch to origin.",
    },
    "merge": {
        "main 병합/푸시 결과를 기록했습니다.": "Recorded the main merge/push result.",
        "파일 브랜치를 main에 통합하고 main을 푸시합니다.": "Integrates the file branch into main and pushes main.",
    },
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
    if "name" in enriched:
        enriched["name"] = _localized_command_label(str(enriched.get("name") or ""))
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
        return ["No new diff files were detected in this step."]

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
        return ["This was recorded as a review step, but no review findings could be summarized."]
    if phase == "review_fix":
        return ["This implementation step addresses changes requested during review."]
    return []


def technical_considerations(
    graph: dict[str, Any],
    prompt: str,
    response: str,
) -> list[dict[str, str]]:
    text = f"{prompt}\n{response}\n{_files_text(graph)}".lower()
    checks: list[tuple[str, str, list[str]]] = [
        (
            "Review loop",
            "Keeps implementation and review results connected in the same session flow.",
            ["review", "리뷰", "검토", "finding", "actionable"],
        ),
        (
            "Session persistence",
            "Stores and reloads groups by conversation thread and project root.",
            ["session", "세션", "thread", "group", "store", "capture"],
        ),
        (
            "Diff boundary",
            "Reduces session noise by isolating files from the current capture within the cumulative branch diff.",
            ["diff", "branch", "delta", "git", "변경"],
        ),
        (
            "UI flow",
            "Prioritizes implementation/review steps and the final summary over file-level details.",
            ["frontend", "react", "ui", "화면", "패널", "flow", "visual"],
        ),
        (
            "Backend API",
            "Extends the FastAPI contract to return the graph and session summary together.",
            ["backend", "api", "fastapi", "router", "service"],
        ),
        (
            "Automation skill",
            "Lets Codex and Claude skills record session events in the local backend without an external LLM.",
            ["skill", "codex", "claude", "capture", "automation"],
        ),
        (
            "Verification",
            "Uses focused tests and type checks to catch session summary and rendering regressions.",
            ["test", "pytest", "typecheck", "검증", "테스트"],
        ),
        (
            "Data model",
            "Separates group, phase, summary, and graph data so visualizations and detail panels share the same facts.",
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
        "added": "Added",
        "modified": "Modified",
        "deleted": "Deleted",
        "renamed": "Renamed",
    }.get(status, status or "Changed")


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
        legacy_generated = _is_legacy_generated_run(run)
        steps: list[dict[str, Any]] = []
        for step in run.get("steps") or []:
            if not isinstance(step, dict):
                continue
            cleaned_step = deepcopy(step)
            if legacy_generated:
                kind = str(cleaned_step.get("kind") or "")
                if "label" in cleaned_step:
                    cleaned_step["label"] = _localized_step_label(
                        kind, str(cleaned_step.get("label") or "")
                    )
                if "summary" in cleaned_step:
                    cleaned_step["summary"] = _localized_step_summary(
                        kind, str(cleaned_step.get("summary") or "")
                    )
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
        "markdown-branch-push": "Markdown Branch Push",
        "markdown-branch-commit": "Markdown Branch Commit",
        "captured-turn": "Captured turn",
        "codeflow": "Codeflow capture",
        "general": "General capture",
        "Markdown Branch Push": "Markdown Branch Push",
        "Markdown Branch Commit": "Markdown Branch Commit",
        "Captured turn": "Captured turn",
        "Markdown 브랜치 푸시": "Markdown Branch Push",
        "Markdown 브랜치 커밋": "Markdown Branch Commit",
        "캡처된 턴": "Captured turn",
        "Codeflow 작업 기록": "Codeflow capture",
        "일반 작업 기록": "General capture",
    }
    cleaned = label.strip() or skill.strip()
    return known.get(cleaned, known.get(skill.strip(), cleaned))


def _localized_command_label(label: str) -> str:
    cleaned = label.strip()
    replacements = {
        "Markdown 브랜치 푸시": "Markdown Branch Push",
        "Markdown 브랜치 커밋": "Markdown Branch Commit",
        "캡처된 턴": "Captured turn",
    }
    for source, target in replacements.items():
        if cleaned == source or cleaned.startswith(f"{source} · "):
            return target + cleaned[len(source):]
    return cleaned


def _is_legacy_generated_run(run: dict[str, Any]) -> bool:
    return str(run.get("skill_label") or "").strip() in {
        "Markdown 브랜치 푸시",
        "Markdown 브랜치 커밋",
        "캡처된 턴",
        "Codeflow 작업 기록",
        "일반 작업 기록",
    } or _localized_command_label(str(run.get("command_label") or "")) != str(
        run.get("command_label") or ""
    ).strip()


def _localized_step_label(kind: str, value: str) -> str:
    cleaned = value.strip()
    legacy = LEGACY_STEP_LABELS.get(kind)
    return legacy[1] if legacy and cleaned == legacy[0] else cleaned


def _localized_step_summary(kind: str, value: str) -> str:
    cleaned = value.strip()
    known = LEGACY_STEP_SUMMARIES.get(kind, {}).get(cleaned)
    if known:
        return known
    if kind not in {"implementation", "review_fix"}:
        return cleaned
    match = re.fullmatch(r"(\d+)개 파일 diff를 기록했습니다\.", cleaned)
    if match:
        count = int(match.group(1))
        return f"Recorded a diff for {count} file{'s' if count != 1 else ''}."
    match = re.fullmatch(r"(\d+)개 파일을 변경했습니다\.", cleaned)
    if match:
        count = int(match.group(1))
        return f"Changed {count} file{'s' if count != 1 else ''}."
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
