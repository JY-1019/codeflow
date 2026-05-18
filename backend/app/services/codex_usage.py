"""Read local Codex token usage from ~/.codex session logs.

Codeflow Light never calls a Codex/OpenAI API for this. The desktop app only
summarizes token_count events that Codex Desktop already wrote locally.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


USAGE_KEYS = (
    "input_tokens",
    "cached_input_tokens",
    "output_tokens",
    "reasoning_output_tokens",
    "total_tokens",
)


@dataclass
class _CodexSessionUsage:
    id: str
    path: Path
    cwd: str = ""
    thread_name: str = ""
    updated_at: str = ""
    is_subagent: bool = False
    usage: dict[str, int] | None = None
    rate_limits: dict[str, Any] | None = None


def codex_usage_summary(project_root: Optional[str] = None) -> dict[str, Any]:
    codex_home = _codex_home()
    sessions_dir = codex_home / "sessions"
    warnings: list[str] = []

    if not sessions_dir.exists():
        return {
            "available": False,
            "updated_at": None,
            "scanned_sessions": 0,
            "all_time": _empty_usage(),
            "current_session": None,
            "rate_limits": None,
            "warnings": [f"Codex session directory not found: {sessions_dir}"],
        }

    thread_names = _read_thread_names(codex_home / "session_index.jsonl")
    sessions = _read_session_usages(sessions_dir, thread_names, warnings)
    sessions_with_usage = [session for session in sessions if session.usage]
    current = _find_current_session(sessions_with_usage, project_root)
    rate_limits_session = current or _latest_session_with_rate_limits(sessions_with_usage)

    latest_updated_at = max((s.updated_at for s in sessions_with_usage if s.updated_at), default=None)
    return {
        "available": bool(sessions_with_usage),
        "updated_at": latest_updated_at,
        "scanned_sessions": len(sessions),
        "all_time": _sum_usage(s.usage for s in sessions_with_usage),
        "current_session": _session_payload(current) if current else None,
        "rate_limits": rate_limits_session.rate_limits if rate_limits_session else None,
        "warnings": warnings[:8],
    }


def _codex_home() -> Path:
    raw = os.getenv("CODEX_HOME", "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".codex"


def _read_thread_names(index_path: Path) -> dict[str, str]:
    names: dict[str, str] = {}
    if not index_path.exists():
        return names
    try:
        with index_path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                session_id = str(item.get("id") or "")
                thread_name = str(item.get("thread_name") or "")
                if session_id and thread_name:
                    names[session_id] = thread_name
    except OSError:
        return names
    return names


def _read_session_usages(
    sessions_dir: Path,
    thread_names: dict[str, str],
    warnings: list[str],
) -> list[_CodexSessionUsage]:
    sessions: list[_CodexSessionUsage] = []
    for path in sessions_dir.rglob("*.jsonl"):
        try:
            session = _read_one_session(path, thread_names)
        except OSError as exc:
            warnings.append(f"could not read {path.name}: {exc}")
            continue
        if session:
            sessions.append(session)
    return sessions


def _read_one_session(
    path: Path,
    thread_names: dict[str, str],
) -> _CodexSessionUsage | None:
    session = _CodexSessionUsage(id=_id_from_path(path), path=path)
    latest_usage: dict[str, int] | None = None
    latest_rate_limits: dict[str, Any] | None = None
    latest_token_timestamp = ""

    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            if item.get("type") == "session_meta":
                payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
                meta_id = str(payload.get("id") or "")
                if meta_id:
                    session.id = meta_id
                session.cwd = str(payload.get("cwd") or "")
                session.is_subagent = (
                    payload.get("thread_source") == "subagent"
                    or isinstance(payload.get("source"), dict)
                    and payload.get("source", {}).get("subagent") is not None
                )
                session.updated_at = str(item.get("timestamp") or payload.get("timestamp") or "")
                continue

            usage = _extract_total_usage(item)
            if usage:
                latest_usage = usage
                latest_rate_limits = _extract_rate_limits(item)
                latest_token_timestamp = str(item.get("timestamp") or "")

    if latest_usage is None:
        return None

    session.usage = latest_usage
    session.rate_limits = latest_rate_limits
    session.thread_name = thread_names.get(session.id, "")
    if latest_token_timestamp:
        session.updated_at = latest_token_timestamp
    return session


def _extract_total_usage(item: dict[str, Any]) -> dict[str, int] | None:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    if payload.get("type") != "token_count":
        return None
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    raw_usage = info.get("total_token_usage")
    if not isinstance(raw_usage, dict):
        return None
    return {key: int(raw_usage.get(key) or 0) for key in USAGE_KEYS}


def _extract_rate_limits(item: dict[str, Any]) -> dict[str, Any] | None:
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    if payload.get("type") != "token_count":
        return None
    raw = payload.get("rate_limits")
    if not isinstance(raw, dict):
        return None
    return {
        "limit_id": str(raw.get("limit_id") or ""),
        "limit_name": raw.get("limit_name"),
        "plan_type": raw.get("plan_type"),
        "rate_limit_reached_type": raw.get("rate_limit_reached_type"),
        "credits": raw.get("credits"),
        "primary": _rate_limit_window(raw.get("primary")),
        "secondary": _rate_limit_window(raw.get("secondary")),
    }


def _rate_limit_window(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    return {
        "used_percent": _optional_float(raw.get("used_percent")),
        "window_minutes": _optional_int(raw.get("window_minutes")),
        "resets_at": _optional_int(raw.get("resets_at")),
    }


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _find_current_session(
    sessions: list[_CodexSessionUsage],
    project_root: Optional[str],
) -> _CodexSessionUsage | None:
    if not sessions:
        return None

    target_root = _resolve_path(project_root) if project_root else None
    candidates = [session for session in sessions if not session.is_subagent]
    if target_root:
        matching = [
            session
            for session in candidates
            if session.cwd and _resolve_path(session.cwd) == target_root
        ]
        if matching:
            return max(matching, key=_session_sort_key)

    return max(candidates or sessions, key=_session_sort_key)


def _latest_session_with_rate_limits(
    sessions: list[_CodexSessionUsage],
) -> _CodexSessionUsage | None:
    sessions_with_limits = [session for session in sessions if session.rate_limits]
    if not sessions_with_limits:
        return None
    return max(sessions_with_limits, key=_session_sort_key)


def _resolve_path(raw: str | None) -> Path | None:
    if not raw:
        return None
    try:
        return Path(raw).expanduser().resolve()
    except OSError:
        return Path(raw).expanduser()


def _session_sort_key(session: _CodexSessionUsage) -> tuple[str, float]:
    try:
        mtime = session.path.stat().st_mtime
    except OSError:
        mtime = 0.0
    return (session.updated_at, mtime)


def _session_payload(session: _CodexSessionUsage) -> dict[str, Any]:
    return {
        "id": session.id,
        "thread_name": session.thread_name,
        "cwd": session.cwd,
        "updated_at": session.updated_at or None,
        "usage": session.usage or _empty_usage(),
        "rate_limits": session.rate_limits,
    }


def _sum_usage(usages: Any) -> dict[str, int]:
    total = _empty_usage()
    for usage in usages:
        if not usage:
            continue
        for key in USAGE_KEYS:
            total[key] += int(usage.get(key) or 0)
    return total


def _empty_usage() -> dict[str, int]:
    return {key: 0 for key in USAGE_KEYS}


def _id_from_path(path: Path) -> str:
    stem = path.stem
    if "-" not in stem:
        return stem
    return stem.rsplit("-", 1)[-1]
