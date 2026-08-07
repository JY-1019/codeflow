from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from .insights import enrich_session_response

MAX_GROUPS_PER_SESSION = 200
WORKFLOW_STEP_ORDER = {
    "preflight": 10,
    "markdown": 20,
    "branch": 30,
    "implementation": 40,
    "review": 50,
    "review_fix": 60,
    "verification": 70,
    "commit": 80,
    "push": 90,
    "merge": 100,
}
WORKFLOW_SKILL_LABELS = {
    "markdown-branch-push": "Markdown Branch Push",
    "markdown-branch-commit": "Markdown Branch Commit",
    "captured-turn": "Captured turn",
    "codeflow": "Codeflow capture",
    "general": "General capture",
}

# Which coding tool/agent actually performed a step. The host tool (Claude Code
# or Codex) implements, while review can be delegated to another agent (e.g. the
# Codex review plugin run from inside Claude Code), so this lives on the step.
AGENT_LABELS = {
    "claude-code": "Claude Code",
    "claude": "Claude Code",
    "codex": "Codex",
    "codex-cli": "Codex",
    "gpt-5": "Codex",
}

_LOCK = threading.Lock()


def _empty_state() -> dict[str, Any]:
    return {"schema_version": 1, "latest_session_id": None, "sessions": {}}


def _state_dir() -> Path:
    configured = os.getenv("CODEFLOW_STATE_DIR", "").strip()
    path = Path(configured or "~/.codeflow").expanduser()
    legacy_configured = os.getenv("CODEFLOW_LIGHT_STATE_DIR", "").strip()
    legacy = Path(legacy_configured or "~/.codeflow-light").expanduser()
    _migrate_legacy_state(path, legacy)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _state_file() -> Path:
    return _state_dir() / "sessions.json"


def _migrate_legacy_state(path: Path, legacy: Path) -> None:
    if not legacy.exists() or legacy.resolve() == path.resolve():
        return
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(path))
        _normalize_state_file(path / "sessions.json")
        return

    legacy_file = legacy / "sessions.json"
    if not legacy_file.exists():
        return
    target_file = path / "sessions.json"
    old_state = _load_state_file(legacy_file)
    state = _load_state_file(target_file) if target_file.exists() else _empty_state()
    if old_state is None or state is None:
        return
    _normalize_state_names(old_state)
    _normalize_state_names(state)

    old_sessions = old_state.get("sessions")
    sessions = state.setdefault("sessions", {})
    if not isinstance(old_sessions, dict) or not isinstance(sessions, dict):
        return
    for session_id, old_session in old_sessions.items():
        if not isinstance(old_session, dict):
            continue
        if session_id in sessions and isinstance(sessions[session_id], dict):
            _merge_session_history(sessions[session_id], old_session)
        elif session_id not in sessions:
            sessions[session_id] = deepcopy(old_session)
    if not state.get("latest_session_id") and old_state.get("latest_session_id") in sessions:
        state["latest_session_id"] = old_state["latest_session_id"]
    _write_state_file(target_file, state)
    legacy_file.unlink()
    try:
        legacy.rmdir()
    except OSError:
        pass


def _merge_session_history(session: dict[str, Any], old_session: dict[str, Any]) -> None:
    groups = session.setdefault("groups", [])
    old_groups = old_session.get("groups", [])
    if not isinstance(groups, list) or not isinstance(old_groups, list):
        return

    old_latest_group_id = str(old_session.get("latest_group_id") or "")
    migrated_latest_group_id = ""
    for old_group in old_groups:
        if not isinstance(old_group, dict):
            continue
        migrated = deepcopy(old_group)
        group_id = str(migrated.get("id") or "legacy-group")
        existing = next(
            (group for group in groups if isinstance(group, dict) and group.get("id") == group_id),
            None,
        )
        target_group_id = group_id
        if existing == migrated:
            pass
        elif existing is not None:
            suffix = 1
            while True:
                migrated["id"] = f"{group_id}-legacy-{suffix}"
                target_group_id = migrated["id"]
                collision = next(
                    (
                        group
                        for group in groups
                        if isinstance(group, dict) and group.get("id") == migrated["id"]
                    ),
                    None,
                )
                if collision == migrated:
                    break
                if collision is None:
                    groups.append(migrated)
                    break
                suffix += 1
        else:
            groups.append(migrated)
        if group_id == old_latest_group_id:
            migrated_latest_group_id = target_group_id

    if not session.get("latest_group_id") and migrated_latest_group_id:
        session["latest_group_id"] = migrated_latest_group_id
    if not session.get("latest_full_graph") and old_session.get("latest_full_graph"):
        session["latest_full_graph"] = deepcopy(old_session["latest_full_graph"])


def _load_state_file(path: Path) -> Optional[dict[str, Any]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _write_state_file(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _normalize_state_names(state: dict[str, Any]) -> bool:
    changed = False
    sessions = state.get("sessions", {})
    if not isinstance(sessions, dict):
        return False
    for session in sessions.values():
        if not isinstance(session, dict):
            continue
        for group in session.get("groups", []):
            if not isinstance(group, dict):
                continue
            for run in group.get("workflow_runs", []):
                if not isinstance(run, dict):
                    continue
                if run.get("skill") == "codeflow-light":
                    run["skill"] = "codeflow"
                    changed = True
                if run.get("skill_label") == "Codeflow Light":
                    run["skill_label"] = "Codeflow"
                    changed = True
    return changed


def _normalize_state_file(path: Path) -> None:
    state = _load_state_file(path)
    if state is not None and _normalize_state_names(state):
        _write_state_file(path, state)


def _read_state() -> dict[str, Any]:
    path = _state_file()
    if not path.exists():
        return _empty_state()
    data = _load_state_file(path)
    if data is None:
        return _empty_state()
    data.setdefault("schema_version", 1)
    data.setdefault("latest_session_id", None)
    data.setdefault("sessions", {})
    _normalize_state_names(data)
    return data


def _write_state(state: dict[str, Any]) -> None:
    _write_state_file(_state_file(), state)


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


def resolve_workflow_run_id(run_id: str = "", markdown_path: str = "", markdown_title: str = "") -> str:
    return _clean_id(run_id) or _default_run_id(markdown_path, markdown_title)


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
        session["latest_group_id"] = group["id"]
        state["latest_session_id"] = resolved_session_id
        _write_state(state)

    return _session_response(session, latest_group_id=group["id"])


def append_workflow_event(
    *,
    project_root: str,
    graph: dict[str, Any],
    full_graph: Optional[dict[str, Any]] = None,
    session_id: Optional[str] = None,
    workflow_id: str = "",
    run_id: str = "",
    user_prompt: str = "",
    skill: str = "",
    skill_label: str = "",
    command_label: str = "",
    markdown_path: str = "",
    markdown_title: str = "",
    markdown_content: str = "",
    branch_name: str = "",
    step_id: str = "",
    step_kind: str = "",
    step_label: str = "",
    step_summary: str = "",
    step_detail: str = "",
    step_status: str = "completed",
    agent: str = "",
    agent_label: str = "",
    files: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Append one live workflow event to a persistent session group.

    A workflow group represents one Markdown review-loop command. Each event is
    stored as a concrete step node, so the UI can render Markdown -> implement
    -> review -> review-fix -> verify/commit/push as the work happens instead
    of reconstructing the loop from a final answer.
    """
    now = datetime.now().astimezone()
    resolved_session_id = (session_id or "").strip() or default_session_id(project_root)
    resolved_workflow_id = (
        _clean_id(workflow_id) or f"workflow-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
    )
    resolved_run_id = resolve_workflow_run_id(run_id, markdown_path, markdown_title)
    normalized_kind = _clean_step_kind(step_kind)
    step_sequence = WORKFLOW_STEP_ORDER.get(normalized_kind, 500)
    resolved_agent = _clean_agent(agent)
    resolved_agent_label = _agent_label(resolved_agent, agent_label)

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
        group = _find_workflow_group(groups, resolved_workflow_id)
        if group is None:
            group = {
                "id": f"group-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
                "workflow_id": resolved_workflow_id,
                "name": command_label.strip()
                or markdown_title.strip()
                or markdown_path.strip()
                or now.strftime("%Y-%m-%d %H:%M:%S"),
                "created_at": now.isoformat(timespec="seconds"),
                "project_root": project_root,
                "user_prompt": user_prompt.strip(),
                "assistant_response": "",
                "graph": graph,
                "workflow_runs": [],
                "workflow_events": [],
            }
            groups.append(group)
            if len(groups) > MAX_GROUPS_PER_SESSION:
                del groups[: len(groups) - MAX_GROUPS_PER_SESSION]

        if user_prompt.strip() and not str(group.get("user_prompt") or "").strip():
            group["user_prompt"] = user_prompt.strip()
        group["project_root"] = project_root
        group["updated_at"] = now.isoformat(timespec="seconds")
        group["graph"] = graph

        run = _find_or_create_run(
            group,
            run_id=resolved_run_id,
            skill=skill,
            skill_label=skill_label,
            command_label=command_label,
            markdown_path=markdown_path,
            markdown_title=markdown_title,
            markdown_content=markdown_content,
            branch_name=branch_name,
        )
        run_steps = run.setdefault("steps", [])
        resolved_step_id = _clean_id(step_id) or _next_step_id(group, resolved_run_id, normalized_kind)
        existing_index = _find_step_index(run_steps, resolved_step_id)
        step_agent = resolved_agent
        step_agent_label = resolved_agent_label
        if existing_index >= 0 and not step_agent:
            existing_agent = str(run_steps[existing_index].get("agent") or "")
            existing_label = str(run_steps[existing_index].get("agent_label") or "")
            step_agent = existing_agent
            step_agent_label = _agent_label(existing_agent, agent_label or existing_label)
        elif existing_index >= 0 and not agent_label.strip():
            existing_agent = str(run_steps[existing_index].get("agent") or "")
            existing_label = str(run_steps[existing_index].get("agent_label") or "")
            if step_agent == existing_agent and existing_label:
                step_agent_label = existing_label
        event_order = (
            _int_value(run_steps[existing_index].get("event_order"), _next_event_order(group))
            if existing_index >= 0
            else _next_event_order(group)
        )
        step_files = files if files is not None else _changed_files(graph)
        step_graph = _scope_graph_to_files(graph, step_files)
        step = {
            "id": resolved_step_id,
            "kind": normalized_kind,
            "label": step_label.strip() or _default_step_label(normalized_kind),
            "summary": step_summary.strip() or _default_step_summary(normalized_kind, step_files),
            "detail": step_detail.strip(),
            "status": _clean_status(step_status),
            "agent": step_agent,
            "agent_label": step_agent_label,
            "files": step_files,
            "created_at": now.isoformat(timespec="seconds"),
            "sequence": step_sequence,
            "event_order": event_order,
            "graph": step_graph,
        }
        event = {
            "id": f"event-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
            "created_at": step["created_at"],
            "workflow_id": resolved_workflow_id,
            "run_id": resolved_run_id,
            "step": _event_step(step),
        }
        group.setdefault("workflow_events", []).append(event)

        if existing_index >= 0:
            run_steps[existing_index] = step
        else:
            run_steps.append(step)
        run_steps.sort(key=lambda item: _int_value(item.get("event_order"), 0))
        run["status"] = _workflow_run_status(run, run_steps)
        run["latest_full_graph"] = full_graph or graph
        group["assistant_response"] = _workflow_event_response(group)
        session["latest_full_graph"] = full_graph or graph
        session["latest_group_id"] = group["id"]
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


def get_latest_workflow_full_graph(
    project_root: str,
    *,
    session_id: Optional[str] = None,
    workflow_id: str = "",
    run_id: str = "",
    markdown_path: str = "",
    markdown_title: str = "",
) -> Optional[dict[str, Any]]:
    session = _find_session(project_root, session_id)
    if not session:
        return None

    groups = session.get("groups") or []
    group = _find_workflow_group(groups, _clean_id(workflow_id))
    if group is None:
        return None

    resolved_run_id = resolve_workflow_run_id(run_id, markdown_path, markdown_title)
    for run in group.get("workflow_runs") or []:
        if isinstance(run, dict) and run.get("id") == resolved_run_id:
            latest = run.get("latest_full_graph")
            return latest if isinstance(latest, dict) else None
    return None


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
            return _session_response(session, latest_group_id=_latest_group_id(session))
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
    return _session_response(session, latest_group_id=_latest_group_id(session))


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
        "groups": _response_groups(session.get("groups", [])),
        "latest_group_id": latest_group_id,
    })


def _response_groups(groups: Any) -> list[dict[str, Any]]:
    if not isinstance(groups, list):
        return []
    response_groups: list[dict[str, Any]] = []
    for group in groups:
        if not isinstance(group, dict):
            continue
        response_group = deepcopy(group)
        response_group.pop("workflow_events", None)
        response_groups.append(response_group)
    return response_groups


def _latest_group_id(session: dict[str, Any]) -> Optional[str]:
    groups = session.get("groups") or []
    stored = str(session.get("latest_group_id") or "")
    if stored and any(isinstance(group, dict) and group.get("id") == stored for group in groups):
        return stored
    return groups[-1]["id"] if groups else None


def _find_workflow_group(groups: list[dict[str, Any]], workflow_id: str) -> Optional[dict[str, Any]]:
    for group in groups:
        if isinstance(group, dict) and group.get("workflow_id") == workflow_id:
            return group
    return None


def _event_step(step: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in step.items() if key != "graph"}


def _find_or_create_run(
    group: dict[str, Any],
    *,
    run_id: str,
    skill: str,
    skill_label: str,
    command_label: str,
    markdown_path: str,
    markdown_title: str,
    markdown_content: str,
    branch_name: str,
) -> dict[str, Any]:
    runs = group.setdefault("workflow_runs", [])
    localized_skill_label = _workflow_skill_label(skill, skill_label)
    for run in runs:
        if isinstance(run, dict) and run.get("id") == run_id:
            _fill_missing_run_fields(
                run,
                skill=skill,
                skill_label=localized_skill_label,
                command_label=command_label,
                markdown_path=markdown_path,
                markdown_title=markdown_title,
                markdown_content=markdown_content,
                branch_name=branch_name,
            )
            return run

    run = {
        "id": run_id,
        "skill": skill.strip(),
        "skill_label": localized_skill_label,
        "command_label": _localized_command_label(
            command_label.strip() or markdown_title.strip() or markdown_path.strip() or run_id
        ),
        "markdown_path": markdown_path.strip(),
        "markdown_title": markdown_title.strip(),
        "markdown_content": markdown_content.strip(),
        "branch_name": branch_name.strip(),
        "status": "in_progress",
        "steps": [],
    }
    runs.append(run)
    return run


def _fill_missing_run_fields(run: dict[str, Any], **values: str) -> None:
    for key, value in values.items():
        cleaned = value.strip()
        if cleaned and not str(run.get(key) or "").strip():
            run[key] = cleaned
    run["skill_label"] = _workflow_skill_label(
        str(run.get("skill") or ""),
        str(run.get("skill_label") or ""),
    )
    if str(run.get("command_label") or "").strip():
        run["command_label"] = _localized_command_label(str(run.get("command_label") or ""))
    if not str(run.get("command_label") or "").strip():
        run["command_label"] = (
            str(run.get("markdown_title") or "").strip()
            or str(run.get("markdown_path") or "").strip()
            or str(run.get("id") or "").strip()
        )


def _find_step_index(steps: list[dict[str, Any]], step_id: str) -> int:
    for index, step in enumerate(steps):
        if isinstance(step, dict) and step.get("id") == step_id:
            return index
    return -1


def _next_step_id(group: dict[str, Any], run_id: str, kind: str) -> str:
    count = 1
    for run in group.get("workflow_runs") or []:
        if not isinstance(run, dict) or run.get("id") != run_id:
            continue
        for step in run.get("steps") or []:
            if isinstance(step, dict) and str(step.get("kind") or "") == kind:
                count += 1
    return f"{kind}-{count}"


def _next_event_order(group: dict[str, Any]) -> int:
    latest = 0
    for run in group.get("workflow_runs") or []:
        if not isinstance(run, dict):
            continue
        for step in run.get("steps") or []:
            if isinstance(step, dict):
                latest = max(latest, _int_value(step.get("event_order"), 0))
    return latest + 1


def _int_value(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _default_run_id(markdown_path: str, markdown_title: str) -> str:
    raw = markdown_path.strip() or markdown_title.strip() or "current-markdown"
    return _clean_id(raw) or "current-markdown"


def _clean_id(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._:-/" else "-" for ch in value.strip())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:120]


def _clean_step_kind(value: str) -> str:
    cleaned = value.strip().lower()
    return cleaned if cleaned in WORKFLOW_STEP_ORDER else "implementation"


def _clean_status(value: str) -> str:
    cleaned = value.strip().lower()
    return cleaned if cleaned in {"completed", "skipped", "pending", "blocked", "unknown"} else "completed"


def _clean_agent(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value.strip().lower())
    cleaned = "-".join(part for part in cleaned.split("-") if part)
    return cleaned[:60]


def _agent_label(agent: str, label: str) -> str:
    cleaned_label = label.strip()
    if cleaned_label:
        return cleaned_label
    if not agent:
        return ""
    return AGENT_LABELS.get(agent, agent.replace("-", " ").replace("_", " ").strip().title())


def _default_step_label(kind: str) -> str:
    return {
        "preflight": "Preflight",
        "markdown": "Parse Markdown command",
        "branch": "Prepare work branch",
        "implementation": "Implementation",
        "review": "Run review",
        "review_fix": "Apply review fixes",
        "verification": "Verification",
        "commit": "Commit",
        "push": "Push branch",
        "merge": "Merge/push main",
    }.get(kind, kind)


def _default_step_summary(kind: str, files: list[str]) -> str:
    if kind in {"implementation", "review_fix"} and files:
        count = len(files)
        return f"Recorded a diff for {count} file{'s' if count != 1 else ''}."
    return {
        "preflight": "Checked the repository and review prerequisites.",
        "markdown": "Recorded the Markdown request as an implementation unit.",
        "branch": "Prepared a work branch for the Markdown unit.",
        "implementation": "Recorded the implementation step.",
        "review": "Recorded the review result.",
        "review_fix": "Recorded the review-fix step.",
        "verification": "Recorded the verification result.",
        "commit": "Recorded the commit result.",
        "push": "Recorded the branch push result.",
        "merge": "Recorded the main merge/push result.",
    }.get(kind, "Recorded a workflow step event.")


def _workflow_skill_label(skill: str, label: str) -> str:
    cleaned = label.strip() or skill.strip()
    known = {
        **WORKFLOW_SKILL_LABELS,
        "Markdown 브랜치 푸시": "Markdown Branch Push",
        "Markdown 브랜치 커밋": "Markdown Branch Commit",
        "캡처된 턴": "Captured turn",
        "Codeflow 작업 기록": "Codeflow capture",
        "일반 작업 기록": "General capture",
    }
    return known.get(cleaned, known.get(skill.strip(), cleaned))


def _localized_command_label(label: str) -> str:
    cleaned = label.strip()
    replacements = {
        "Markdown 브랜치 푸시": "Markdown Branch Push",
        "Markdown 브랜치 커밋": "Markdown Branch Commit",
        "캡처된 턴": "Captured turn",
    }
    for source, target in replacements.items():
        if cleaned == source or cleaned.startswith(f"{source} · "):
            return target + cleaned[len(source):]
    return cleaned


def _changed_files(graph: dict[str, Any]) -> list[str]:
    files: list[str] = []
    for node in graph.get("nodes") or []:
        if (
            isinstance(node, dict)
            and node.get("kind") == "changed"
            and node.get("symbol_kind") == "file"
            and node.get("file")
        ):
            files.append(str(node["file"]))
    return _unique(files)


def _scope_graph_to_files(graph: dict[str, Any], files: list[str]) -> dict[str, Any]:
    scoped = deepcopy(graph)
    allowed_files = {file for file in files if file}
    nodes = scoped.get("nodes") if isinstance(scoped.get("nodes"), list) else []
    edges = scoped.get("edges") if isinstance(scoped.get("edges"), list) else []
    if not allowed_files:
        scoped["nodes"] = []
        scoped["edges"] = []
        return scoped

    kept_nodes: list[dict[str, Any]] = []
    kept_ids: set[str] = set()
    for node in nodes:
        if not isinstance(node, dict) or str(node.get("file") or "") not in allowed_files:
            continue
        kept_nodes.append(node)
        node_id = str(node.get("id") or "")
        if node_id:
            kept_ids.add(node_id)

    scoped["nodes"] = kept_nodes
    scoped["edges"] = [
        edge
        for edge in edges
        if (
            isinstance(edge, dict)
            and str(edge.get("source") or "") in kept_ids
            and str(edge.get("target") or "") in kept_ids
        )
    ]
    return scoped


def _workflow_run_status(run: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    statuses = {str(step.get("status") or "") for step in steps if isinstance(step, dict)}
    if "blocked" in statuses:
        return "blocked"
    terminal_statuses = {
        str(step.get("kind") or ""): str(step.get("status") or "")
        for step in steps
        if isinstance(step, dict)
    }
    done = {"completed", "skipped"}
    if str(run.get("skill") or "") == "markdown-branch-push":
        if terminal_statuses.get("push") in done and terminal_statuses.get("merge") in done:
            return "completed"
        return "in_progress"
    if str(run.get("skill") or "") in {"general", "codeflow"}:
        if terminal_statuses.get("verification") in done:
            return "completed"
        return "in_progress"
    if terminal_statuses.get("commit") in done:
        return "completed"
    return "in_progress"


def _workflow_event_response(group: dict[str, Any]) -> str:
    lines: list[str] = []
    for run in group.get("workflow_runs") or []:
        if not isinstance(run, dict):
            continue
        for step in run.get("steps") or []:
            if not isinstance(step, dict):
                continue
            summary = str(step.get("summary") or "").strip()
            if summary:
                lines.append(f"{_default_step_label(str(step.get('kind') or ''))}: {summary}")
    return "\n".join(_unique(lines))


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
