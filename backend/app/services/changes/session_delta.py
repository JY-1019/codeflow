"""Filter a full diff graph down to the changes introduced since last capture."""
from __future__ import annotations

import re
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

from .graph_builder import ChangeEdge, ChangeGraph, ChangeNode


def filter_graph_to_session_delta(
    graph: ChangeGraph,
    previous_full_graph: dict[str, Any] | None,
    assistant_response: str = "",
) -> None:
    """Mutate `graph` so a session group only shows this response's changes.

    Session captures use `source=branch`, which is intentionally cumulative.
    To keep each group readable, compare the current full graph to the previous
    full snapshot and keep only the file nodes directly modified by this turn.
    """
    previous_nodes = {
        str(node.get("id")): node
        for node in (previous_full_graph or {}).get("nodes", [])
        if isinstance(node, dict) and node.get("id")
    }

    file_nodes = [
        node
        for node in graph.nodes
        if node.kind == "changed" and node.symbol_kind == "file" and node.file
    ]
    file_nodes_by_file = {node.file: node for node in file_nodes}
    reverted_nodes = _reverted_file_nodes(previous_nodes, file_nodes_by_file)
    if reverted_nodes:
        graph.nodes.extend(reverted_nodes)
        file_nodes.extend(reverted_nodes)
        file_nodes_by_file.update({node.file: node for node in reverted_nodes})

    changed_files = _changed_files_since_previous(graph, previous_nodes)
    changed_files |= {node.file for node in reverted_nodes if node.file}

    for node in file_nodes:
        if node.file not in changed_files:
            continue

        previous = previous_nodes.get(node.id)
        if previous and node.snippet and _node_changed_since_previous(node, previous):
            delta_snippet = _delta_snippet(node.snippet, str(previous.get("snippet") or ""))
            if delta_snippet:
                node.snippet = delta_snippet
                node.added_lines = _count_prefixed(delta_snippet, "+ ")
                node.removed_lines = _count_prefixed(delta_snippet, "- ")

    file_node_ids = {
        node.id
        for node in graph.nodes
        if node.kind == "changed" and node.symbol_kind == "file" and node.file in changed_files
    }

    if not file_node_ids:
        graph.nodes = []
        graph.edges = []
        graph.warnings.append("no new diff since previous session group")
        return

    nodes_by_id = {node.id: node for node in graph.nodes}
    graph.nodes = [node for node in graph.nodes if node.id in file_node_ids]
    graph.edges = _lift_edges_to_changed_files(graph.edges, nodes_by_id, file_nodes_by_file, changed_files)


def serialized_graph_snapshot(graph: ChangeGraph) -> dict[str, Any]:
    """Return a compact full graph snapshot for future delta comparisons."""
    return {
        "project_root": graph.project_root,
        "source": graph.source,
        "base_ref": graph.base_ref,
        "head_ref": graph.head_ref,
        "warnings": list(graph.warnings),
        "nodes": [asdict(node) for node in graph.nodes],
        "edges": [asdict(edge) for edge in graph.edges],
    }


def _lift_edges_to_changed_files(
    edges: list[ChangeEdge],
    nodes_by_id: dict[str, ChangeNode],
    file_nodes_by_file: dict[str, ChangeNode],
    changed_files: set[str],
) -> list[ChangeEdge]:
    """Keep relationships between changed files after symbol nodes are hidden."""
    lifted: list[ChangeEdge] = []
    seen: set[tuple[str, str, str, str]] = set()

    for edge in edges:
        source_node = nodes_by_id.get(edge.source)
        target_node = nodes_by_id.get(edge.target)
        if not source_node or not target_node:
            continue
        if not source_node.file or not target_node.file:
            continue
        if source_node.file == target_node.file:
            continue
        if source_node.file not in changed_files or target_node.file not in changed_files:
            continue

        source_file_node = file_nodes_by_file.get(source_node.file)
        target_file_node = file_nodes_by_file.get(target_node.file)
        if not source_file_node or not target_file_node:
            continue

        key = (source_file_node.id, target_file_node.id, edge.kind, "")
        if key in seen:
            continue
        seen.add(key)

        if edge.source == source_file_node.id and edge.target == target_file_node.id:
            lifted.append(edge)
            continue

        lifted.append(
            replace(
                edge,
                id=f"{edge.id}::file-level",
                source=source_file_node.id,
                target=target_file_node.id,
                summary=_file_edge_summary(source_node, target_node, edge),
                body=_file_edge_body(source_node, target_node, edge),
            )
        )
    return lifted


def _file_edge_summary(source_node: ChangeNode, target_node: ChangeNode, edge: ChangeEdge) -> str:
    if edge.kind == "calls":
        return f"`{source_node.file}` 의 `{source_node.label}` 가 `{target_node.file}` 의 `{target_node.label}` 를 호출합니다."
    if edge.kind == "referenced_by":
        return f"`{source_node.file}` 가 `{target_node.file}` 의 변경 심볼 `{target_node.label}` 를 참조합니다."
    return f"`{source_node.file}` 와 `{target_node.file}` 사이의 {edge.kind} 관계입니다."


def _file_edge_body(source_node: ChangeNode, target_node: ChangeNode, edge: ChangeEdge) -> str:
    return "\n".join(
        [
            f"- **관계**: {edge.kind}",
            f"- **출발 파일**: `{source_node.file}`",
            f"- **출발 코드**: `{source_node.label}`",
            f"- **도착 파일**: `{target_node.file}`",
            f"- **도착 코드**: `{target_node.label}`",
        ]
    )


def _node_changed_since_previous(node: ChangeNode, previous: dict[str, Any] | None) -> bool:
    if previous is None:
        return True
    return (
        node.status != previous.get("status")
        or node.snippet != (previous.get("snippet") or "")
        or node.added_lines != int(previous.get("added_lines") or 0)
        or node.removed_lines != int(previous.get("removed_lines") or 0)
    )


def _changed_files_since_previous(
    graph: ChangeGraph,
    previous_nodes: dict[str, dict[str, Any]],
) -> set[str]:
    file_nodes = [
        node
        for node in graph.nodes
        if node.kind == "changed" and node.symbol_kind == "file" and node.file
    ]
    if not previous_nodes:
        return {node.file for node in file_nodes}

    changed_files: set[str] = set()
    for node in graph.nodes:
        if node.kind != "changed" or not node.file:
            continue
        if _node_changed_since_previous(node, previous_nodes.get(node.id)):
            changed_files.add(node.file)
    return changed_files


def _reverted_file_nodes(
    previous_nodes: dict[str, dict[str, Any]],
    current_file_nodes_by_file: dict[str, ChangeNode],
) -> list[ChangeNode]:
    reverted: list[ChangeNode] = []
    for previous in previous_nodes.values():
        if previous.get("kind") != "changed" or previous.get("symbol_kind") != "file":
            continue
        file = str(previous.get("file") or "")
        if not file or file in current_file_nodes_by_file:
            continue

        previous_snippet = str(previous.get("snippet") or "")
        snippet = _revert_snippet(previous_snippet)
        added_lines = _count_prefixed(snippet, "+ ")
        removed_lines = _count_prefixed(snippet, "- ")
        reverted.append(
            ChangeNode(
                id=str(previous.get("id") or f"file::{file.replace('/', '__').replace('.', '_')}"),
                kind="changed",
                label=str(previous.get("label") or Path(file).name),
                file=file,
                language=str(previous.get("language") or ""),
                symbol_kind="file",
                status="modified",
                summary="기존 세션 변경을 되돌림",
                body="이 파일은 이전 capture에 있던 branch diff에서 사라져, base 상태로 되돌아간 단계로 기록됩니다.",
                snippet=snippet,
                added_lines=added_lines,
                removed_lines=removed_lines,
            )
        )
    return reverted


def _revert_snippet(snippet: str) -> str:
    output: list[str] = []
    for line in snippet.splitlines():
        if line.startswith("+ "):
            output.append("- " + line[2:])
        elif line.startswith("- "):
            output.append("+ " + line[2:])
        else:
            output.append(line)
    return "\n".join(output).strip()


def _delta_snippet(current: str, previous: str) -> str:
    previous_hunks = _snippet_hunks(previous)
    current_hunks = _snippet_hunks(current)
    previous_change_lines = {line for hunk in previous_hunks for line in hunk["changes"]}
    current_change_lines = {line for hunk in current_hunks for line in hunk["changes"]}
    if not previous_change_lines:
        return current

    output: list[str] = []
    matched_previous_indexes: set[int] = set()

    for index, current_hunk in enumerate(current_hunks):
        previous_index = _matching_previous_hunk_index(
            current_hunk,
            previous_hunks,
            preferred_index=index,
            already_matched=matched_previous_indexes,
        )
        previous_hunk = previous_hunks[previous_index] if previous_index is not None else None
        if previous_index is not None:
            matched_previous_indexes.add(previous_index)

        new_changes = [
            line for line in current_hunk["changes"] if line not in previous_change_lines
        ]
        removed_previous_additions = (
            _removed_previous_additions(previous_hunk["changes"], current_change_lines)
            if previous_hunk
            else []
        )
        lines_to_keep = _delta_hunk_rows(
            current_hunk["rows"],
            set(new_changes),
            removed_previous_additions,
        )
        if lines_to_keep:
            output.append(current_hunk["header"])
            output.extend(lines_to_keep)
            output.append("")

    for index, previous_hunk in enumerate(previous_hunks):
        if index in matched_previous_indexes:
            continue
        reverted_changes = _reversed_rows_missing_from_current(
            previous_hunk["rows"],
            current_change_lines,
        )
        if reverted_changes:
            output.append(previous_hunk["header"])
            output.extend(_unique_lines(reverted_changes))
            output.append("")

    return "\n".join(output).strip()


def _snippet_hunks(snippet: str) -> list[dict[str, Any]]:
    hunks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in snippet.splitlines():
        if line.startswith("@@"):
            current = {"header": line, "changes": [], "rows": []}
            hunks.append(current)
            continue
        if not line.startswith(("+ ", "- ", "  ")):
            continue
        if current is None:
            current = {"header": "", "changes": [], "rows": []}
            hunks.append(current)
        current["rows"].append(line)
        if line.startswith(("+ ", "- ")):
            current["changes"].append(line)
    return hunks


def _matching_previous_hunk_index(
    current_hunk: dict[str, Any],
    previous_hunks: list[dict[str, Any]],
    preferred_index: int,
    already_matched: set[int],
) -> int | None:
    if preferred_index < len(previous_hunks) and preferred_index not in already_matched:
        preferred = previous_hunks[preferred_index]
        if _hunks_overlap(current_hunk["header"], preferred["header"]):
            return preferred_index

    for index, previous_hunk in enumerate(previous_hunks):
        if index in already_matched:
            continue
        if _hunks_overlap(current_hunk["header"], previous_hunk["header"]):
            return index
    return None


def _hunks_overlap(current_header: str, previous_header: str) -> bool:
    current_range = _old_range(current_header)
    previous_range = _old_range(previous_header)
    if not current_range or not previous_range:
        return current_header == previous_header

    current_start, current_end = current_range
    previous_start, previous_end = previous_range
    return current_start <= previous_end and previous_start <= current_end


def _old_range(header: str) -> tuple[int, int] | None:
    match = re.search(r"@@ -(?P<start>\d+)(?:,(?P<count>\d+))?", header)
    if not match:
        return None
    start = int(match.group("start"))
    count = int(match.group("count") or "1")
    if count <= 0:
        return (start, start)
    return (start, start + count - 1)


def _removed_previous_additions(
    previous_changes: list[str],
    current_change_lines: set[str],
) -> list[str]:
    return [
        "- " + line[2:]
        for line in previous_changes
        if line.startswith("+ ") and line not in current_change_lines
    ]


def _delta_hunk_rows(
    current_rows: list[str],
    new_changes: set[str],
    removed_previous_additions: list[str],
) -> list[str]:
    if not new_changes and not removed_previous_additions:
        return []
    rows: list[str] = []
    rows.extend(removed_previous_additions)
    for line in current_rows:
        if line.startswith("  ") or line in new_changes:
            rows.append(line)
    return rows


def _reversed_rows_missing_from_current(
    previous_rows: list[str],
    current_change_lines: set[str],
) -> list[str]:
    reverted: list[str] = []
    has_reverted_change = False
    for line in previous_rows:
        if line.startswith("  "):
            reverted.append(line)
            continue
        if line in current_change_lines:
            continue
        if line.startswith("+ "):
            reverted.append("- " + line[2:])
            has_reverted_change = True
        elif line.startswith("- "):
            reverted.append("+ " + line[2:])
            has_reverted_change = True
    return reverted if has_reverted_change else []


def _unique_lines(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        unique.append(line)
    return unique


def _count_prefixed(snippet: str, prefix: str) -> int:
    return sum(1 for line in snippet.splitlines() if line.startswith(prefix))
