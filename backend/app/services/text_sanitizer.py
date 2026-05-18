from __future__ import annotations

import re
from typing import Any


MAX_CAPTURE_TEXT_CHARS = 12_000
MAX_CAPTURE_LINE_CHARS = 520

_CODEX_WARNING_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\S+\s+WARN\s+"
    r"(?:codex_|codex_protocol::|codex_core_plugins::|codex_core_skills::)"
)
_MANIFEST_WARNING_RE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\S+\s+WARN\s+.*"
    r"(?:interface\.defaultPrompt|interface\.icon_|model_messages is missing)"
)
_COMMAND_STATUS_RE = re.compile(
    r"(?:^|\s)(?:succeeded|failed|exited) in \d+ms:?\s*$",
    re.IGNORECASE,
)
_COMMAND_CONTEXT_RE = re.compile(
    r'^(?=.*(?:\b(?:sed|cat|rg|git|npm|python\d?|pytest|bash|sh|ls|find|nl|wc)\b|&&|\|\|))'
    r'.*"\s+in\s+/.*$'
)
_TOOL_METADATA_RE = re.compile(
    r"^(?:Chunk ID:|Wall time:|Process exited with code|Original token count:)"
)
_PRIORITY_FINDING_RE = re.compile(r"^(?:[-*]\s*)?\[P[0-3]\]", re.IGNORECASE)
_REVIEW_BOUNDARY_RE = re.compile(
    r"^(?:#{1,3}\s*)?"
    r"(?:Findings|Review|Summary|Tests?|Verification|Open Questions|"
    r"리뷰|검토|요약|검증|테스트|질문)\b",
    re.IGNORECASE,
)


def clean_captured_text(text: str, max_chars: int = MAX_CAPTURE_TEXT_CHARS) -> str:
    """Remove Codex runtime noise and oversized tool transcripts from captured text."""
    if not text:
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    cleaned: list[str] = []
    skipping_tool_output = False
    omitted_noise = False
    metadata_countdown = 0

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if _is_codex_runtime_warning(stripped):
            omitted_noise = True
            continue

        if stripped == "[output truncated]":
            omitted_noise = True
            skipping_tool_output = True
            continue

        if _TOOL_METADATA_RE.match(stripped):
            omitted_noise = True
            metadata_countdown = 4
            continue

        if metadata_countdown > 0:
            metadata_countdown -= 1
            if stripped == "Output:":
                omitted_noise = True
                skipping_tool_output = True
                continue

        if _looks_like_command_output_start(stripped):
            omitted_noise = True
            skipping_tool_output = True
            continue

        if skipping_tool_output:
            if _is_review_boundary(stripped):
                skipping_tool_output = False
            else:
                omitted_noise = True
                continue

        if len(line) > MAX_CAPTURE_LINE_CHARS:
            line = line[: MAX_CAPTURE_LINE_CHARS - 3].rstrip() + "..."
            omitted_noise = True

        cleaned.append(line)

    result = _trim_blank_edges("\n".join(cleaned))
    if len(result) > max_chars:
        result = (
            result[: max_chars - len(_truncation_notice())]
            .rstrip()
            + _truncation_notice()
        )

    if result:
        return result
    if omitted_noise:
        return "_Codeflow Light가 Codex 내부 경고와 긴 도구 출력을 생략했습니다._"
    return ""


def clean_graph_docs(graph: dict[str, Any]) -> dict[str, Any]:
    """Clean already-serialized graph docs when loading older noisy sessions."""
    graph["narrative"] = clean_captured_text(str(graph.get("narrative") or ""))
    graph["assistant_response"] = clean_captured_text(
        str(graph.get("assistant_response") or "")
    )

    for collection_name in ("nodes", "edges"):
        collection = graph.get(collection_name)
        if not isinstance(collection, list):
            continue
        for item in collection:
            if not isinstance(item, dict):
                continue
            if "body" in item:
                item["body"] = clean_captured_text(str(item.get("body") or ""))
            if "summary" in item:
                item["summary"] = _single_line_summary(str(item.get("summary") or ""))

    return graph


def _is_codex_runtime_warning(line: str) -> bool:
    return bool(_CODEX_WARNING_RE.match(line) or _MANIFEST_WARNING_RE.match(line))


def _looks_like_command_output_start(line: str) -> bool:
    return bool(_COMMAND_STATUS_RE.search(line) or _COMMAND_CONTEXT_RE.search(line))


def _is_review_boundary(line: str) -> bool:
    if not line:
        return False
    return bool(
        _PRIORITY_FINDING_RE.match(line)
        or _REVIEW_BOUNDARY_RE.match(line)
        or "No findings" in line
        or "actionable finding" in line.lower()
    )


def _single_line_summary(text: str) -> str:
    cleaned = clean_captured_text(text, max_chars=280)
    return " ".join(cleaned.split())


def _trim_blank_edges(text: str) -> str:
    lines = text.split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def _truncation_notice() -> str:
    return "\n\n_Codeflow Light가 긴 Codex 리뷰 출력의 나머지를 생략했습니다._"
