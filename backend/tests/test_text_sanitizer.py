from __future__ import annotations

from app.services.text_sanitizer import clean_captured_text


def test_clean_captured_text_removes_codex_warnings():
    text = (
        "리뷰 요약\n"
        "2026-05-18T01:43:07.107045Z  WARN codex_core_plugins::manifest: "
        "ignoring interface.defaultPrompt: maximum of 3 prompts is supported\n"
        "- 정상 문장"
    )

    cleaned = clean_captured_text(text)

    assert "codex_core_plugins" not in cleaned
    assert "정상 문장" in cleaned


def test_clean_captured_text_collapses_truncated_tool_output_until_review_boundary():
    text = (
        "[output truncated]\n"
        "sed -n '1,360p' frontend/src/flow/utils/positions.ts\" "
        "in /Users/a86466/workspace/codeflow\n"
        " succeeded in 0ms:\n"
        "import type { Node } from '@xyflow/react';\n"
        "export function noisy() {}\n"
        "Findings\n"
        "- [P2] 중요한 finding은 남아야 합니다.\n"
    )

    cleaned = clean_captured_text(text)

    assert "중요한 finding" in cleaned
    assert "export function noisy" not in cleaned
    assert "output truncated" not in cleaned


def test_clean_captured_text_caps_long_text():
    cleaned = clean_captured_text(("리뷰 본문\n" * 2_000), max_chars=1_000)

    assert len(cleaned) <= 1_000
    assert "나머지를 생략" in cleaned


def test_clean_captured_text_preserves_normal_path_sentences():
    text = 'I changed "positions.ts" in /Users/a86466/workspace/codeflow.'

    assert clean_captured_text(text) == text
