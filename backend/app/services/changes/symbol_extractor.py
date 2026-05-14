"""Lightweight symbol extraction.

Goal: for each changed hunk, identify which function/class/method it lives in
so we can build a node-per-symbol graph instead of a node-per-file graph.

We use cheap regex-based detection rather than parsing a full AST. This is
intentional — codeflow-light should not require tree-sitter or language-specific
toolchains. For unknown languages we fall back to file-level nodes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from .git_diff import FileChange, GitDiffResult


@dataclass
class SymbolSpan:
    name: str
    kind: str  # function | method | class | module
    start_line: int
    end_line: int
    signature: str = ""


_PY_DEF = re.compile(r"^(?P<indent>\s*)(?:async\s+)?def\s+(?P<name>[A-Za-z_][\w]*)\s*\(")
_PY_CLASS = re.compile(r"^(?P<indent>\s*)class\s+(?P<name>[A-Za-z_][\w]*)\b")
_TS_FUNC = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?function\s+(?P<name>[A-Za-z_$][\w$]*)\s*\("
)
_TS_ARROW = re.compile(
    r"^\s*(?:export\s+)?(?:const|let|var)\s+(?P<name>[A-Za-z_$][\w$]*)\s*[:=]"
)
_TS_CLASS = re.compile(
    r"^\s*(?:export\s+)?(?:abstract\s+)?class\s+(?P<name>[A-Za-z_$][\w$]*)"
)
_TS_METHOD = re.compile(
    r"^\s*(?:public|private|protected|static|async|readonly|\s)*\s*(?P<name>[A-Za-z_$][\w$]*)\s*\([^)]*\)\s*[:{]?"
)
_GO_FUNC = re.compile(r"^\s*func\s+(?:\([^)]*\)\s+)?(?P<name>[A-Za-z_][\w]*)\s*\(")
_JAVA_METHOD = re.compile(
    r"^\s*(?:public|private|protected|static|final|abstract|synchronized|\s)+"
    r"[\w<>,\[\]\s]+\s+(?P<name>[A-Za-z_][\w]*)\s*\([^)]*\)\s*(?:throws[\w\s,]+)?\{"
)
_JAVA_CLASS = re.compile(r"^\s*(?:public|private|protected|abstract|final|\s)*class\s+(?P<name>[A-Za-z_][\w]*)")


def extract_symbols(content: str, language: str) -> list[SymbolSpan]:
    if not content:
        return []
    lines = content.splitlines()
    if language == "python":
        return _extract_python(lines)
    if language in {"typescript", "javascript"}:
        return _extract_ts(lines)
    if language == "go":
        return _extract_brace(lines, _GO_FUNC, kind="function")
    if language == "java":
        return _extract_brace_multi(lines, [(_JAVA_METHOD, "method"), (_JAVA_CLASS, "class")])
    return []


def _extract_python(lines: list[str]) -> list[SymbolSpan]:
    spans: list[SymbolSpan] = []
    stack: list[tuple[int, SymbolSpan]] = []

    def close_to(indent: int, end_line: int) -> None:
        while stack and stack[-1][0] >= indent:
            _, span = stack.pop()
            span.end_line = end_line
            spans.append(span)

    for idx, line in enumerate(lines, start=1):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        match = _PY_DEF.match(line)
        if match:
            close_to(indent, idx - 1)
            kind = "method" if any(stack) else "function"
            span = SymbolSpan(
                name=match.group("name"),
                kind=kind,
                start_line=idx,
                end_line=idx,
                signature=line.strip(),
            )
            stack.append((indent, span))
            continue
        match = _PY_CLASS.match(line)
        if match:
            close_to(indent, idx - 1)
            span = SymbolSpan(
                name=match.group("name"),
                kind="class",
                start_line=idx,
                end_line=idx,
                signature=line.strip(),
            )
            stack.append((indent, span))

    close_to(-1, len(lines))
    spans.sort(key=lambda s: s.start_line)
    return spans


def _extract_ts(lines: list[str]) -> list[SymbolSpan]:
    spans: list[SymbolSpan] = []
    brace_depth = 0
    open_spans: list[tuple[int, SymbolSpan]] = []

    for idx, line in enumerate(lines, start=1):
        opens_before = brace_depth
        matched = None
        for pattern, kind in (
            (_TS_CLASS, "class"),
            (_TS_FUNC, "function"),
            (_TS_ARROW, "function"),
        ):
            m = pattern.match(line)
            if m:
                matched = (m.group("name"), kind)
                break
        if matched and "{" in line:
            span = SymbolSpan(
                name=matched[0],
                kind=matched[1],
                start_line=idx,
                end_line=idx,
                signature=line.strip(),
            )
            open_spans.append((opens_before, span))
        brace_depth += line.count("{") - line.count("}")
        while open_spans and brace_depth <= open_spans[-1][0]:
            _, span = open_spans.pop()
            span.end_line = idx
            spans.append(span)

    for _, span in open_spans:
        span.end_line = len(lines)
        spans.append(span)

    spans.sort(key=lambda s: s.start_line)
    return spans


def _extract_brace(lines: list[str], pattern: re.Pattern[str], kind: str) -> list[SymbolSpan]:
    spans: list[SymbolSpan] = []
    open_spans: list[tuple[int, SymbolSpan]] = []
    brace_depth = 0
    for idx, line in enumerate(lines, start=1):
        before = brace_depth
        m = pattern.match(line)
        if m and "{" in line:
            span = SymbolSpan(
                name=m.group("name"),
                kind=kind,
                start_line=idx,
                end_line=idx,
                signature=line.strip(),
            )
            open_spans.append((before, span))
        brace_depth += line.count("{") - line.count("}")
        while open_spans and brace_depth <= open_spans[-1][0]:
            _, span = open_spans.pop()
            span.end_line = idx
            spans.append(span)
    for _, span in open_spans:
        span.end_line = len(lines)
        spans.append(span)
    spans.sort(key=lambda s: s.start_line)
    return spans


def _extract_brace_multi(
    lines: list[str], patterns: list[tuple[re.Pattern[str], str]]
) -> list[SymbolSpan]:
    spans: list[SymbolSpan] = []
    open_spans: list[tuple[int, SymbolSpan]] = []
    brace_depth = 0
    for idx, line in enumerate(lines, start=1):
        before = brace_depth
        for pattern, kind in patterns:
            m = pattern.match(line)
            if m and "{" in line:
                span = SymbolSpan(
                    name=m.group("name"),
                    kind=kind,
                    start_line=idx,
                    end_line=idx,
                    signature=line.strip(),
                )
                open_spans.append((before, span))
                break
        brace_depth += line.count("{") - line.count("}")
        while open_spans and brace_depth <= open_spans[-1][0]:
            _, span = open_spans.pop()
            span.end_line = idx
            spans.append(span)
    for _, span in open_spans:
        span.end_line = len(lines)
        spans.append(span)
    spans.sort(key=lambda s: s.start_line)
    return spans


def find_enclosing_symbol(spans: list[SymbolSpan], line: int) -> Optional[SymbolSpan]:
    candidates = [s for s in spans if s.start_line <= line <= s.end_line]
    if not candidates:
        return None
    candidates.sort(key=lambda s: s.end_line - s.start_line)
    return candidates[0]
