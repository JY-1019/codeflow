"""Map an LLM assistant response onto the change graph.

The backend never calls an LLM. Instead it receives the raw text the LLM
(Codex / Claude Code / anything) already produced when it made the change,
and links each paragraph of that explanation to the node it talks about.

Heuristics, in order:

1. Split the response into paragraphs (blank line) and fenced code blocks.
2. For every paragraph, scan for:
   - file paths matching a node's `file` (basename or full path)
   - symbol identifiers matching a node's `label`
3. Attach the paragraph to every matched node's `body` (joined with `\n\n`).
   If multiple nodes match, the paragraph is shared (best effort).
4. Paragraphs that match nothing become part of the graph-level `narrative`.
5. Inline code spans like `foo()` or `path/to/file.py` boost match weight.

Pure-Python, no LLM, no FlowForge.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .graph_builder import ChangeEdge, ChangeGraph, ChangeNode


_CODE_FENCE_RE = re.compile(r"^```")
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


@dataclass
class _Paragraph:
    text: str
    inline_tokens: list[str]
    is_code_block: bool


def _split_paragraphs(response: str) -> list[_Paragraph]:
    """Split into paragraphs, keeping fenced code blocks as their own paragraph."""
    paragraphs: list[_Paragraph] = []
    if not response.strip():
        return paragraphs

    lines = response.splitlines()
    buffer: list[str] = []
    in_code = False
    code_buffer: list[str] = []

    def flush_buffer() -> None:
        if not buffer:
            return
        text = "\n".join(buffer).strip()
        buffer.clear()
        if not text:
            return
        inline = [m.group(1).strip() for m in _INLINE_CODE_RE.finditer(text)]
        paragraphs.append(_Paragraph(text=text, inline_tokens=inline, is_code_block=False))

    def flush_code() -> None:
        if not code_buffer:
            return
        text = "\n".join(code_buffer).strip("\n")
        code_buffer.clear()
        if not text:
            return
        paragraphs.append(
            _Paragraph(
                text="```\n" + text + "\n```",
                inline_tokens=[],
                is_code_block=True,
            )
        )

    for line in lines:
        if _CODE_FENCE_RE.match(line):
            if in_code:
                flush_code()
                in_code = False
            else:
                flush_buffer()
                in_code = True
            continue
        if in_code:
            code_buffer.append(line)
            continue
        if line.strip() == "":
            flush_buffer()
        else:
            buffer.append(line)
    flush_buffer()
    if in_code:
        flush_code()
    return paragraphs


def _node_candidates(node: ChangeNode) -> list[str]:
    """Tokens that, if they appear in a paragraph, count as a hit for this node."""
    candidates: set[str] = set()
    if node.file:
        candidates.add(node.file)
        candidates.add(Path(node.file).name)
        stem = Path(node.file).stem
        if stem and stem != node.label:
            candidates.add(stem)
    if node.label and node.label != Path(node.file).name:
        candidates.add(node.label)
    return [c for c in candidates if c]


def _score_paragraph(paragraph: _Paragraph, candidates: list[str]) -> tuple[int, list[str]]:
    """Return (score, matched_candidates).

    Inline-code mentions weigh 3, plain text mentions weigh 1, an identifier-only
    token surrounded by word boundaries weighs 1 extra.
    """
    if paragraph.is_code_block:
        return (0, [])
    text = paragraph.text
    matched: list[str] = []
    score = 0
    for cand in candidates:
        if not cand:
            continue
        if cand in paragraph.inline_tokens:
            score += 3
            matched.append(cand)
            continue
        if cand in text:
            score += 1
            matched.append(cand)
            continue
        if _IDENT_RE.fullmatch(cand):
            if re.search(r"\b" + re.escape(cand) + r"\b", text):
                score += 1
                matched.append(cand)
    return (score, matched)


def attach_response(
    graph: ChangeGraph,
    assistant_response: str,
) -> ChangeGraph:
    """Mutate `graph`: fill node.body / node.summary / graph.narrative based on
    the assistant response. Safe to call when response is empty."""
    response = (assistant_response or "").strip()
    if not response:
        return graph

    paragraphs = _split_paragraphs(response)
    if not paragraphs:
        graph.narrative = response
        return graph

    node_paragraphs: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
    paragraph_used = [False] * len(paragraphs)

    for node in graph.nodes:
        candidates = _node_candidates(node)
        if not candidates:
            continue
        scored: list[tuple[int, int]] = []
        for idx, paragraph in enumerate(paragraphs):
            score, _ = _score_paragraph(paragraph, candidates)
            if score > 0:
                scored.append((score, idx))
        scored.sort(reverse=True)
        for _, idx in scored[:3]:
            node_paragraphs[node.id].append(paragraphs[idx].text)
            paragraph_used[idx] = True

    for node in graph.nodes:
        attached = node_paragraphs.get(node.id) or []
        if not attached:
            continue
        first = attached[0]
        if not node.summary:
            node.summary = _first_sentence(first)
        body = "\n\n".join(attached)
        node.body = (node.body + "\n\n" + body).strip() if node.body else body

    _attach_edge_response_docs(graph, paragraphs, paragraph_used)

    unmatched = [p.text for idx, p in enumerate(paragraphs) if not paragraph_used[idx]]
    graph.narrative = "\n\n".join(unmatched).strip() if unmatched else response

    _propagate_edge_docs(graph)
    return graph


def _attach_edge_response_docs(
    graph: ChangeGraph,
    paragraphs: list[_Paragraph],
    paragraph_used: list[bool],
) -> None:
    nodes_by_id: dict[str, ChangeNode] = {n.id: n for n in graph.nodes}

    for edge in graph.edges:
        src = nodes_by_id.get(edge.source)
        tgt = nodes_by_id.get(edge.target)
        if not src or not tgt:
            continue

        src_candidates = _node_candidates(src)
        tgt_candidates = _node_candidates(tgt)
        relation_candidates = [edge.kind, edge.label, "import" if edge.kind == "imports" else ""]
        attached: list[tuple[int, int]] = []

        for idx, paragraph in enumerate(paragraphs):
            src_score, _ = _score_paragraph(paragraph, src_candidates)
            tgt_score, _ = _score_paragraph(paragraph, tgt_candidates)
            relation_score, _ = _score_paragraph(
                paragraph,
                [candidate for candidate in relation_candidates if candidate],
            )
            if src_score > 0 and tgt_score > 0:
                attached.append((src_score + tgt_score + relation_score, idx))
            elif relation_score > 0 and (src_score > 0 or tgt_score > 0):
                attached.append((src_score + tgt_score + relation_score, idx))

        if not attached:
            continue

        attached.sort(reverse=True)
        texts = [paragraphs[idx].text for _, idx in attached[:2]]
        for _, idx in attached[:2]:
            paragraph_used[idx] = True

        response_doc = "\n\n".join(texts)
        addition = f"**Details mapped from the AI response:**\n\n{response_doc}"
        edge.body = (edge.body + "\n\n" + addition).strip() if edge.body else addition


def _propagate_edge_docs(graph: ChangeGraph) -> None:
    """Give each edge a short summary based on its endpoints' summaries.

    No LLM: just human-readable defaults so the doc panel isn't blank.
    """
    nodes_by_id: dict[str, ChangeNode] = {n.id: n for n in graph.nodes}
    for edge in graph.edges:
        src = nodes_by_id.get(edge.source)
        tgt = nodes_by_id.get(edge.target)
        if not src or not tgt:
            continue
        if edge.summary:
            continue
        verb = {
            "contains": "contains",
            "calls": "calls/references",
            "imports": "imports",
            "referenced_by": "uses",
            "modifies": "modifies",
            "renamed_from": "was renamed to",
        }.get(edge.kind, "is connected to")
        edge.summary = f"`{src.label}` {verb} `{tgt.label}`."
        if not edge.body and (src.summary or tgt.summary):
            parts: list[str] = []
            if src.summary:
                parts.append(f"- **{src.label}**: {src.summary}")
            if tgt.summary:
                parts.append(f"- **{tgt.label}**: {tgt.summary}")
            edge.body = "\n".join(parts)


_SENTENCE_END = re.compile(r"(?<=[\.!?。！？])\s+|\n")


def _first_sentence(text: str, limit: int = 140) -> str:
    text = text.strip()
    if not text:
        return ""
    parts = _SENTENCE_END.split(text, maxsplit=1)
    head = parts[0].strip()
    if len(head) > limit:
        head = head[: limit - 1].rstrip() + "…"
    return head


def attach_response_tokens(response: str) -> Iterable[str]:
    """Utility used by tests: identifiers mentioned in inline code spans."""
    return {match.group(1).strip() for match in _INLINE_CODE_RE.finditer(response or "")}
