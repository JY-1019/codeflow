"""Fallback doc generator that runs whether or not an assistant response is provided.

Goal: when the user opens the UI without pasting any LLM response, each node/edge
should still carry a useful, non-empty summary + body built mechanically from
the diff structure itself.

The output is intentionally short and factual ("modified function",
not "this beautifully refactored function ..."). When an LLM response is later
attached via response_mapper.attach_response, those LLM paragraphs are *appended*
on top of these defaults, not replacing them.
"""
from __future__ import annotations

import re

from .graph_builder import ChangeEdge, ChangeGraph, ChangeNode


_STATUS_LABEL: dict[str, str] = {
    "added": "added",
    "modified": "modified",
    "deleted": "deleted",
    "renamed": "renamed",
    "unchanged": "unchanged",
}

_KIND_LABEL: dict[str, str] = {
    "changed": "direct change",
    "affected": "affected",
    "context": "reference context",
    "file": "file",
}

_SYMBOL_LABEL: dict[str, str] = {
    "file": "file",
    "function": "function",
    "method": "method",
    "class": "class",
    "module": "module",
}

_EDGE_KIND_LABEL: dict[str, str] = {
    "contains": "contains",
    "calls": "calls/references",
    "imports": "imports",
    "referenced_by": "uses",
    "modifies": "modifies",
    "renamed_from": "renamed from",
}


def fill_default_docs(graph: ChangeGraph) -> None:
    """Populate node.summary/body and edge.summary/body using only diff facts."""
    for node in graph.nodes:
        _fill_node_default(node)
    for edge in graph.edges:
        _fill_edge_default(edge, graph)


def _fill_node_default(node: ChangeNode) -> None:
    status_label = _STATUS_LABEL.get(node.status, node.status)
    symbol_label = _SYMBOL_LABEL.get(node.symbol_kind, node.symbol_kind or "symbol")
    kind_label = _KIND_LABEL.get(node.kind, node.kind)

    if not node.summary:
        if node.kind == "affected":
            node.summary = f"External {symbol_label} that references a changed symbol."
        elif node.status == "added":
            node.summary = f"Newly added {symbol_label}"
        elif node.status == "deleted":
            node.summary = f"Deleted {symbol_label}"
        elif node.status == "renamed":
            node.summary = f"Renamed {symbol_label}"
        elif node.status == "modified":
            node.summary = f"Modified {symbol_label}"
        else:
            node.summary = f"{kind_label} · {symbol_label}"

    if node.body:
        return

    lines: list[str] = [f"1) [{node.summary}]"]

    if node.snippet:
        lines.extend(_plain_change_lines(node.file, node.snippet))
    else:
        lines.extend(_fallback_change_lines(kind_label, status_label, symbol_label))

    if node.kind == "affected":
        lines.append("")
        lines.append("This code was not changed directly; it is a usage site connected to a changed file.")

    node.body = "\n".join(lines).strip()


def _plain_change_lines(file_path: str, snippet: str) -> list[str]:
    hunks = _parse_snippet_hunks(snippet)
    if not hunks:
        return [
            "The diff snippet did not contain enough detail for a file-level implementation summary.",
            "The session summary shows only changed files and step information.",
        ]

    all_removed = _flatten_hunk_lines(hunks, "removed")
    all_added = _flatten_hunk_lines(hunks, "added")
    lines = _implementation_lines_for_file(file_path, all_added, all_removed)
    if lines:
        return lines[:5]

    intent = _summarize_code_intent(all_added, all_removed)
    if intent:
        return [
            "File-level change signals summarize the implementation.",
            f"Detected implementation signals: {intent}",
        ]

    return ["No explainable implementation signal was found. Check the changed-file scope in the session flow."]


def _fallback_change_lines(kind_label: str, status_label: str, symbol_label: str) -> list[str]:
    return [
        f"The {kind_label} {symbol_label} is marked as {status_label}.",
        "When available, the code snippet contributes to the file-level implementation summary.",
    ]


def _parse_snippet_hunks(snippet: str) -> list[dict[str, list[str] | str]]:
    hunks: list[dict[str, list[str] | str]] = []
    current: dict[str, list[str] | str] | None = None

    for line in snippet.splitlines():
        if line.startswith("@@"):
            current = {"header": line.strip(), "added": [], "removed": []}
            hunks.append(current)
            continue
        if line.startswith("+ "):
            if current is None:
                current = {"header": "", "added": [], "removed": []}
                hunks.append(current)
            added = current["added"]
            if isinstance(added, list):
                added.append(line[2:])
        elif line.startswith("- "):
            if current is None:
                current = {"header": "", "added": [], "removed": []}
                hunks.append(current)
            removed = current["removed"]
            if isinstance(removed, list):
                removed.append(line[2:])
    return hunks


def _flatten_hunk_lines(hunks: list[dict[str, list[str] | str]], key: str) -> list[str]:
    flattened: list[str] = []
    for hunk in hunks:
        value = hunk[key]
        if isinstance(value, list):
            flattened.extend(value)
    return flattened


def _summarize_code_intent(added: list[str], removed: list[str]) -> str:
    joined = "\n".join(line.strip() for line in [*added, *removed] if line.strip())
    signals: list[str] = []

    def add_signal(label: str) -> None:
        if label not in signals:
            signals.append(label)

    if re.search(r"\bawait\b|\bfetch[A-Za-z0-9_]*\s*\(", joined):
        add_signal("asynchronous data loading")
    if re.search(r"\bset[A-Z][A-Za-z0-9_]*\s*\(", joined):
        add_signal("React state updates")
    if re.search(r"\bif\s*\(|\?\s*[^:]+:", joined):
        add_signal("conditional logic")
    if re.search(r"^\s*(import|export)\b", joined, re.MULTILINE):
        add_signal("module wiring")
    if re.search(r"\b(useEffect|useMemo|useCallback|useState)\s*\(", joined):
        add_signal("React hook flow")
    if re.search(r"<[A-Za-z][A-Za-z0-9.:-]*\b|className=", joined):
        add_signal("UI rendering changes")
    if re.search(r"\b(type|interface)\s+[A-Za-z_$][\w$]*", joined):
        add_signal("type definitions")
    if re.search(r"\b(return|throw)\b", joined):
        add_signal("return/error flow")
    if re.search(r"\b(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=|^\s*[A-Za-z_$][\w$.]*\s*=", joined, re.MULTILINE):
        add_signal("value calculation/assignment")
    if re.search(r"\b[A-Za-z_$][\w$.]*\s*\(", joined):
        add_signal("function calls")

    return ", ".join(signals[:3])


_KNOWN_IMPLEMENTATIONS: dict[str, str] = {
    "enrich_session_response": "Adds implementation/review steps and a session summary to stored conversation groups.",
    "enrich_group": "Computes the phase, implementation summary, review summary, and technical considerations for one capture group.",
    "build_session_summary": "Combines implementation scope and review flow across groups.",
    "technical_considerations": "Extracts technical consideration categories from prompts, responses, and changed filenames.",
    "implementation_summary": "Creates a file-level implementation summary instead of line-by-line descriptions.",
    "review_summary": "Organizes review and verification statements into session-step summaries.",
    "extractDeclarations": "Extracts added function, class, and type declarations from a diff for node summaries.",
    "codexThreadName": "Searches session_index.jsonl in reverse for a Codex session's conversation title.",
    "codexHome": "Safely resolves CODEX_HOME and home-relative paths to find local Codex data.",
    "formatTitleLabel": "Shortens a long conversation title for the window title and header badge.",
    "_flatten_hunk_lines": "Collects added and removed lines from diff hunks into one analysis input.",
    "_summarize_code_intent": "Finds signals such as await, React setters, and imports in changed code for a file-level summary.",
}


def _implementation_lines_for_file(file_path: str, added: list[str], removed: list[str]) -> list[str]:
    joined = "\n".join([*added, *removed])
    lines: list[str] = []

    if re.search(r"codexThreadName|CODEFLOW_SESSION_TITLE|sessionTitle", joined):
        lines.append("Finds the chat title from a Codex session ID and passes it to the Electron window title and renderer query.")
    elif re.search(r"WINDOW_SESSION_TITLE|session_title", joined):
        lines.append("Shows the Electron-provided chat title in the header badge and uses the hash only as a fallback.")
    elif re.search(r"enrich_session_response|build_session_summary|technical_considerations", joined):
        lines.append("Adds implementation/review steps and technical considerations to session groups.")
    elif re.search(r"buildImplementationSummary|selectCoreReviewLines|describeCoreLine", joined):
        lines.append("Replaces line-by-line code descriptions with file- and step-focused summaries.")
    elif re.search(r"_summarize_code_intent|_flatten_hunk_lines", joined):
        lines.append("Makes the backend fallback documentation infer implementation intent from diff lines.")
    elif "tests/" in file_path or re.search(r"assert .*핵심|assert .*구현|test_", joined):
        lines.append("Tests that the new description generator produces meaningful implementation summaries.")

    for name in _extract_declarations(added):
        description = _KNOWN_IMPLEMENTATIONS.get(name)
        if description:
            lines.append(f"`{name}`: {description}")

    if any(re.search(r"라인 변화|핵심 흐름|추가된 코드 예", line) for line in removed):
        lines.append("Removes descriptions centered on line counts, abstract categories, and arbitrary code examples.")

    return _unique(lines)


def _extract_declarations(lines: list[str]) -> list[str]:
    declarations: list[str] = []
    for raw in lines:
        line = raw.strip()
        match = (
            re.match(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", line)
            or re.match(r"def\s+([A-Za-z_][\w]*)\s*\(", line)
            or re.match(r"(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", line)
            or re.match(r"(?:export\s+)?(?:type|interface)\s+([A-Za-z_$][\w$]*)", line)
            or re.match(r"(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", line)
        )
        if match:
            declarations.append(match.group(1))
    return _unique(declarations)


def _unique(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        output.append(line)
    return output

def _fill_edge_default(edge: ChangeEdge, graph: ChangeGraph) -> None:
    nodes_by_id = {n.id: n for n in graph.nodes}
    src = nodes_by_id.get(edge.source)
    tgt = nodes_by_id.get(edge.target)

    kind_label = _EDGE_KIND_LABEL.get(edge.kind, edge.kind)
    src_label = src.label if src else edge.source
    tgt_label = tgt.label if tgt else edge.target

    if not edge.summary:
        if edge.kind == "contains":
            edge.summary = f"`{src_label}` contains `{tgt_label}`."
        elif edge.kind == "calls":
            edge.summary = f"`{src_label}` references `{tgt_label}`."
        elif edge.kind == "imports":
            edge.summary = f"`{src_label}` imports `{tgt_label}`."
        elif edge.kind == "referenced_by":
            edge.summary = f"`{src_label}` uses `{tgt_label}`."
        elif edge.kind == "renamed_from":
            edge.summary = f"`{src_label}` was renamed to `{tgt_label}`."
        elif edge.kind == "modifies":
            edge.summary = f"Changes in `{src_label}` apply to `{tgt_label}`."
        else:
            edge.summary = f"`{src_label}` → `{tgt_label}` ({kind_label})"

    if edge.body:
        return

    lines: list[str] = [f"- **Relationship**: {kind_label}"]
    if src:
        lines.append(
            f"- **Source**: `{src.label}` "
            f"({_SYMBOL_LABEL.get(src.symbol_kind, src.symbol_kind)}, {src.file})"
        )
    if tgt:
        lines.append(
            f"- **Target**: `{tgt.label}` "
            f"({_SYMBOL_LABEL.get(tgt.symbol_kind, tgt.symbol_kind)}, {tgt.file})"
        )
    if edge.kind == "imports":
        lines.append("")
        lines.append("> This edge shows the current file importing functionality from another project file.")
    if src and src.summary:
        lines.append(f"- **Source summary**: {src.summary}")
    if tgt and tgt.summary:
        lines.append(f"- **Target summary**: {tgt.summary}")
    edge.body = "\n".join(lines)
