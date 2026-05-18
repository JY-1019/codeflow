from __future__ import annotations

import hashlib
import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from .insights import enrich_session_response

MAX_GROUPS_PER_SESSION = 200

_LOCK = threading.Lock()


def _state_dir() -> Path:
    raw = os.getenv("CODEFLOW_LIGHT_STATE_DIR", "~/.codeflow-light")
    path = Path(raw).expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_file() -> Path:
    return _state_dir() / "sessions.json"


def _empty_state() -> dict[str, Any]:
    return {"schema_version": 1, "latest_session_id": None, "sessions": {}}


def _read_state() -> dict[str, Any]:
    path = _state_file()
    if not path.exists():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    data.setdefault("schema_version", 1)
    data.setdefault("latest_session_id", None)
    data.setdefault("sessions", {})
    return data


def _write_state(state: dict[str, Any]) -> None:
    path = _state_file()
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _current_branch(project_root: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=project_root,
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    return (proc.stdout or "").strip()


def default_session_id(project_root: str) -> str:
    root_hash = hashlib.sha1(project_root.encode("utf-8")).hexdigest()[:10]
    branch = _current_branch(project_root) or "worktree"
    safe_branch = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in branch)
    return f"{root_hash}:{safe_branch}"


def append_group(
    *,
    project_root: str,
    graph: dict[str, Any],
    full_graph: Optional[dict[str, Any]] = None,
    user_prompt: str = "",
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    now = datetime.now().astimezone()
    resolved_session_id = (session_id or "").strip() or default_session_id(project_root)
    group = {
        "id": f"group-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
        "name": now.strftime("%Y-%m-%d %H:%M:%S"),
        "created_at": now.isoformat(timespec="seconds"),
        "project_root": project_root,
        "user_prompt": user_prompt.strip(),
        "assistant_response": graph.get("assistant_response", ""),
        "graph": graph,
    }

    with _LOCK:
        state = _read_state()
        sessions = state.setdefault("sessions", {})
        session = sessions.setdefault(
            resolved_session_id,
            {
                "id": resolved_session_id,
                "project_root": project_root,
                "branch": _current_branch(project_root),
                "created_at": now.isoformat(timespec="seconds"),
                "updated_at": now.isoformat(timespec="seconds"),
                "groups": [],
            },
        )
        session["project_root"] = project_root
        session["branch"] = _current_branch(project_root)
        session["updated_at"] = now.isoformat(timespec="seconds")
        groups = session.setdefault("groups", [])
        groups.append(group)
        if len(groups) > MAX_GROUPS_PER_SESSION:
            del groups[: len(groups) - MAX_GROUPS_PER_SESSION]
        session["latest_full_graph"] = full_graph or graph
        state["latest_session_id"] = resolved_session_id
        _write_state(state)

    return _session_response(session, latest_group_id=group["id"])


def get_latest_full_graph(
    project_root: str,
    session_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    session = _find_session(project_root, session_id)
    if not session:
        return None
    latest_full_graph = session.get("latest_full_graph")
    if isinstance(latest_full_graph, dict):
        return latest_full_graph
    groups = session.get("groups") or []
    if not groups:
        return None
    latest_graph = groups[-1].get("graph")
    return latest_graph if isinstance(latest_graph, dict) else None


def get_latest_session(
    project_root: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict[str, Any]:
    with _LOCK:
        state = _read_state()

    sessions_by_id = state.get("sessions", {})
    if session_id:
        session = sessions_by_id.get(session_id)
        if session:
            groups = session.get("groups", [])
            latest_group_id = groups[-1]["id"] if groups else None
            return _session_response(session, latest_group_id=latest_group_id)
        return {
            "session_id": session_id,
            "project_root": project_root or "",
            "branch": "",
            "groups": [],
            "latest_group_id": None,
        }

    sessions = list(sessions_by_id.values())
    if project_root:
        matches = [s for s in sessions if s.get("project_root") == project_root]
        if not matches:
            return {
                "session_id": None,
                "project_root": project_root,
                "branch": "",
                "groups": [],
                "latest_group_id": None,
            }
        sessions = matches

    if not sessions:
        return {
            "session_id": None,
            "project_root": project_root or "",
            "branch": "",
            "groups": [],
            "latest_group_id": None,
        }

    latest_id = state.get("latest_session_id")
    session = next((s for s in sessions if s.get("id") == latest_id), None)
    if session is None:
        session = max(sessions, key=lambda s: s.get("updated_at", ""))
    groups = session.get("groups", [])
    latest_group_id = groups[-1]["id"] if groups else None
    return _session_response(session, latest_group_id=latest_group_id)


def _find_session(project_root: str, session_id: Optional[str] = None) -> Optional[dict[str, Any]]:
    with _LOCK:
        state = _read_state()

    sessions = state.get("sessions", {})
    if session_id and session_id in sessions:
        return sessions[session_id]
    if session_id:
        return None

    matches = [s for s in sessions.values() if s.get("project_root") == project_root]
    if not matches:
        return None

    latest_id = state.get("latest_session_id")
    latest = next((s for s in matches if s.get("id") == latest_id), None)
    if latest:
        return latest
    return max(matches, key=lambda s: s.get("updated_at", ""))


def _session_response(session: dict[str, Any], latest_group_id: Optional[str]) -> dict[str, Any]:
    return enrich_session_response({
        "session_id": session.get("id"),
        "project_root": session.get("project_root", ""),
        "branch": session.get("branch", ""),
        "groups": session.get("groups", []),
        "latest_group_id": latest_group_id,
    })
