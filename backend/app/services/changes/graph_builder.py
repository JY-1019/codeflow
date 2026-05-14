"""Build the change graph from a parsed git diff.

The graph has three node kinds:
  - changed:  a function/class/file the LLM modified or added
  - affected: a symbol that references a changed symbol (callers)
  - context:  a symbol referenced *by* a changed symbol (callees) when useful

Edges are:
  - modifies:    the change touches this symbol
  - calls:       changed symbol calls another symbol
  - referenced_by: affected symbol references the changed symbol
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from .git_diff import FileChange, GitDiffResult, read_file_content
from .symbol_extractor import SymbolSpan, extract_symbols, find_enclosing_symbol


NodeKind = Literal["changed", "affected", "context", "file"]
ChangeStatus = Literal["added", "modified", "deleted", "renamed", "unchanged"]
EdgeKind = Literal["modifies", "calls", "referenced_by", "contains", "renamed_from"]


@dataclass
class ChangeNode:
    id: str
    kind: NodeKind
    label: str
    file: str
    language: str = ""
    symbol_kind: str = ""  # function | method | class | module | file
    status: ChangeStatus = "unchanged"
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    summary: str = ""
    body: str = ""
    snippet: str = ""
    added_lines: int = 0
    removed_lines: int = 0


@dataclass
class ChangeEdge:
    id: str
    source: str
    target: str
    kind: EdgeKind
    label: str = ""
    summary: str = ""
    body: str = ""


@dataclass
class ChangeGraph:
    project_root: str
    source: str
    base_ref: Optional[str]
    head_ref: Optional[str]
    nodes: list[ChangeNode] = field(default_factory=list)
    edges: list[ChangeEdge] = field(default_factory=list)
    narrative: str = ""
    warnings: list[str] = field(default_factory=list)


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _symbol_node_id(file: str, symbol: str) -> str:
    safe_file = file.replace("/", "__").replace(".", "_")
    return f"sym::{safe_file}::{symbol}"


def _file_node_id(file: str) -> str:
    safe_file = file.replace("/", "__").replace(".", "_")
    return f"file::{safe_file}"


def _snippet_for_hunk(file_change: FileChange) -> str:
    lines: list[str] = []
    for hunk in file_change.hunks:
        lines.append(f"@@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@")
        for ln, text in hunk.removed_lines:
            lines.append(f"- {text}")
        for ln, text in hunk.added_lines:
            lines.append(f"+ {text}")
        lines.append("")
    return "\n".join(lines).strip()


def _snippet_for_symbol(file_change: FileChange, span: SymbolSpan) -> str:
    keep: list[str] = []
    for hunk in file_change.hunks:
        for ln, text in hunk.added_lines:
            if span.start_line <= ln <= span.end_line:
                keep.append(f"+ {text}")
        for ln, text in hunk.removed_lines:
            if span.start_line <= ln <= span.end_line:
                keep.append(f"- {text}")
    return "\n".join(keep[:80]).strip()


def build_graph(diff: GitDiffResult) -> ChangeGraph:
    graph = ChangeGraph(
        project_root=diff.project_root,
        source=diff.source,
        base_ref=diff.base_ref,
        head_ref=diff.head_ref,
        warnings=list(diff.warnings),
    )

    changed_symbols_by_file: dict[str, list[tuple[SymbolSpan, ChangeNode]]] = {}

    for file_change in diff.files:
        added = sum(len(h.added_lines) for h in file_change.hunks)
        removed = sum(len(h.removed_lines) for h in file_change.hunks)

        file_node_id = _file_node_id(file_change.path)
        file_node = ChangeNode(
            id=file_node_id,
            kind="changed",
            label=Path(file_change.path).name,
            file=file_change.path,
            language=file_change.language,
            symbol_kind="file",
            status=file_change.status,
            summary=f"{file_change.status} ({added}+/{removed}-)",
            snippet=_snippet_for_hunk(file_change)[:4000],
            added_lines=added,
            removed_lines=removed,
        )

        if file_change.status == "deleted":
            graph.nodes.append(file_node)
            continue

        content = read_file_content(diff.project_root, file_change.path)
        spans = extract_symbols(content, file_change.language) if content else []

        touched_spans: dict[str, tuple[SymbolSpan, set[int]]] = {}
        for hunk in file_change.hunks:
            for ln, _ in hunk.added_lines:
                span = find_enclosing_symbol(spans, ln)
                if span:
                    entry = touched_spans.setdefault(span.name, (span, set()))
                    entry[1].add(ln)

        if not touched_spans:
            graph.nodes.append(file_node)
            if file_change.old_path and file_change.status == "renamed":
                old_id = _file_node_id(file_change.old_path)
                graph.edges.append(
                    ChangeEdge(
                        id=f"edge::rename::{file_change.path}",
                        source=old_id,
                        target=file_node_id,
                        kind="renamed_from",
                        label="renamed",
                        summary=f"{file_change.old_path} → {file_change.path}",
                    )
                )
            continue

        graph.nodes.append(file_node)
        symbol_nodes: list[tuple[SymbolSpan, ChangeNode]] = []
        for name, (span, lines_touched) in touched_spans.items():
            node_id = _symbol_node_id(file_change.path, name)
            symbol_status: ChangeStatus = "added" if file_change.status == "added" else "modified"
            symbol_node = ChangeNode(
                id=node_id,
                kind="changed",
                label=f"{span.name}",
                file=file_change.path,
                language=file_change.language,
                symbol_kind=span.kind,
                status=symbol_status,
                start_line=span.start_line,
                end_line=span.end_line,
                summary=f"{span.kind} touched at {len(lines_touched)} line(s)",
                snippet=_snippet_for_symbol(file_change, span)[:4000],
                added_lines=len(lines_touched),
            )
            graph.nodes.append(symbol_node)
            symbol_nodes.append((span, symbol_node))

            graph.edges.append(
                ChangeEdge(
                    id=f"edge::contains::{node_id}",
                    source=file_node_id,
                    target=node_id,
                    kind="contains",
                    label="contains",
                    summary=f"{file_change.path} contains {span.name}",
                )
            )

        changed_symbols_by_file[file_change.path] = symbol_nodes

    _add_call_edges(graph, diff, changed_symbols_by_file)
    _add_affected_nodes(graph, diff, changed_symbols_by_file)

    return graph


def _add_call_edges(
    graph: ChangeGraph,
    diff: GitDiffResult,
    changed_symbols_by_file: dict[str, list[tuple[SymbolSpan, ChangeNode]]],
) -> None:
    """For each changed symbol, look at the *added* lines and detect identifiers
    that match other changed symbols. Each match becomes a `calls` edge."""

    all_changed_names: dict[str, list[ChangeNode]] = {}
    for nodes in changed_symbols_by_file.values():
        for _, node in nodes:
            all_changed_names.setdefault(node.label, []).append(node)

    if not all_changed_names:
        return

    for file_change in diff.files:
        symbols = changed_symbols_by_file.get(file_change.path, [])
        if not symbols:
            continue
        for span, node in symbols:
            call_targets: set[str] = set()
            for hunk in file_change.hunks:
                for ln, text in hunk.added_lines:
                    if not (span.start_line <= ln <= span.end_line):
                        continue
                    for token in _IDENT.findall(text):
                        if token == node.label:
                            continue
                        if token in all_changed_names:
                            call_targets.add(token)
            for target_name in call_targets:
                for target_node in all_changed_names[target_name]:
                    if target_node.id == node.id:
                        continue
                    graph.edges.append(
                        ChangeEdge(
                            id=f"edge::calls::{node.id}->{target_node.id}",
                            source=node.id,
                            target=target_node.id,
                            kind="calls",
                            label="calls",
                            summary=f"{node.label} references {target_node.label}",
                        )
                    )


def _add_affected_nodes(
    graph: ChangeGraph,
    diff: GitDiffResult,
    changed_symbols_by_file: dict[str, list[tuple[SymbolSpan, ChangeNode]]],
    max_per_symbol: int = 5,
) -> None:
    """For each changed symbol, grep the repo for references and create
    `affected` nodes for the top files that reference it."""
    if not changed_symbols_by_file:
        return

    project_root = Path(diff.project_root)
    seen_ids: set[str] = {node.id for node in graph.nodes}

    for nodes in changed_symbols_by_file.values():
        for span, node in nodes:
            if node.symbol_kind == "file":
                continue
            references = _grep_references(project_root, node.label, exclude=node.file)
            for ref_file in references[:max_per_symbol]:
                affected_id = _file_node_id(ref_file)
                if affected_id in seen_ids:
                    if not any(
                        edge.source == affected_id and edge.target == node.id
                        for edge in graph.edges
                    ):
                        graph.edges.append(
                            ChangeEdge(
                                id=f"edge::refby::{affected_id}->{node.id}",
                                source=affected_id,
                                target=node.id,
                                kind="referenced_by",
                                label="uses",
                                summary=f"{ref_file} uses {node.label}",
                            )
                        )
                    continue
                graph.nodes.append(
                    ChangeNode(
                        id=affected_id,
                        kind="affected",
                        label=Path(ref_file).name,
                        file=ref_file,
                        language="",
                        symbol_kind="file",
                        status="unchanged",
                        summary=f"references {node.label}",
                    )
                )
                seen_ids.add(affected_id)
                graph.edges.append(
                    ChangeEdge(
                        id=f"edge::refby::{affected_id}->{node.id}",
                        source=affected_id,
                        target=node.id,
                        kind="referenced_by",
                        label="uses",
                        summary=f"{ref_file} uses {node.label}",
                    )
                )


def _grep_references(project_root: Path, symbol: str, exclude: str, limit: int = 20) -> list[str]:
    if not symbol or len(symbol) < 3:
        return []
    pattern = r"\b" + re.escape(symbol) + r"\b"
    try:
        proc = subprocess.run(
            ["git", "grep", "-l", "-E", pattern],
            cwd=str(project_root),
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode not in (0, 1):
        return []
    paths = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    return [p for p in paths if p != exclude][:limit]
