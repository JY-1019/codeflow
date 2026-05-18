from __future__ import annotations

import json
from pathlib import Path

from app.services.codex_usage import codex_usage_summary


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def _token_count(total: int, timestamp: str, limit_percent: float = 7.5) -> dict:
    return {
        "timestamp": timestamp,
        "type": "event_msg",
        "payload": {
            "type": "token_count",
            "info": {
                "total_token_usage": {
                    "input_tokens": total - 30,
                    "cached_input_tokens": 10,
                    "output_tokens": 20,
                    "reasoning_output_tokens": 10,
                    "total_tokens": total,
                }
            },
            "rate_limits": {
                "limit_id": "codex",
                "plan_type": "prolite",
                "primary": {
                    "used_percent": limit_percent,
                    "window_minutes": 300,
                    "resets_at": 1778759604,
                },
                "secondary": {
                    "used_percent": 18,
                    "window_minutes": 10080,
                    "resets_at": 1779201845,
                },
                "credits": None,
                "rate_limit_reached_type": None,
            },
        },
    }


def test_codex_usage_sums_sessions_and_finds_current_project(tmp_path, monkeypatch):
    codex_home = tmp_path / "codex"
    project = tmp_path / "repo"
    project.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    codex_home.mkdir()

    (codex_home / "session_index.jsonl").write_text(
        json.dumps({"id": "main-session", "thread_name": "Codeflow work"}) + "\n",
        encoding="utf-8",
    )
    _write_jsonl(
        codex_home / "sessions" / "2026" / "05" / "14" / "main-session.jsonl",
        [
            {
                "timestamp": "2026-05-14T00:00:00Z",
                "type": "session_meta",
                "payload": {"id": "main-session", "cwd": str(project)},
            },
            _token_count(100, "2026-05-14T00:01:00Z"),
            _token_count(250, "2026-05-14T00:02:00Z"),
        ],
    )
    _write_jsonl(
        codex_home / "sessions" / "2026" / "05" / "14" / "other-session.jsonl",
        [
            {
                "timestamp": "2026-05-14T01:00:00Z",
                "type": "session_meta",
                "payload": {"id": "other-session", "cwd": str(tmp_path / "other")},
            },
            _token_count(400, "2026-05-14T01:02:00Z"),
        ],
    )

    summary = codex_usage_summary(str(project))

    assert summary["available"] is True
    assert summary["all_time"]["total_tokens"] == 650
    assert summary["current_session"]["id"] == "main-session"
    assert summary["current_session"]["thread_name"] == "Codeflow work"
    assert summary["current_session"]["usage"]["total_tokens"] == 250
    assert summary["rate_limits"]["primary"]["used_percent"] == 7.5
    assert summary["rate_limits"]["primary"]["window_minutes"] == 300
    assert summary["current_session"]["rate_limits"]["secondary"]["used_percent"] == 18.0


def test_codex_usage_handles_missing_codex_home(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing"))

    summary = codex_usage_summary(str(tmp_path))

    assert summary["available"] is False
    assert summary["all_time"]["total_tokens"] == 0
    assert summary["current_session"] is None
    assert summary["rate_limits"] is None
    assert summary["warnings"]
