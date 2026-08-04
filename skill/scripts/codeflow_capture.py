#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "http://127.0.0.1:8019/api"
DEFAULT_CAPTURE_TIMEOUT = 30.0


def repo_root() -> Path:
    configured = os.environ.get("CODEFLOW_APP_ROOT", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    script_path = Path(__file__).resolve()
    for start in [script_path.parent, Path.cwd().resolve()]:
        for candidate in [start, *start.parents]:
            if (candidate / "frontend" / "package.json").exists() and (candidate / "backend" / "main.py").exists():
                return candidate

    legacy = script_path.parents[2]
    if (legacy / "frontend" / "package.json").exists():
        return legacy

    raise RuntimeError(
        "Could not find Codeflow app root. Set CODEFLOW_APP_ROOT to the repository path."
    )


def codeflow_executable() -> Path:
    configured = os.environ.get("CODEFLOW_EXECUTABLE", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if path.exists():
            return path.resolve()
        raise RuntimeError(f"CODEFLOW_EXECUTABLE does not exist: {path}")

    script_path = Path(__file__).resolve()
    candidates = [
        script_path.parents[1] / "bin" / "codeflow",
        repo_root() / "skill" / "bin" / "codeflow",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()

    path = shutil.which("codeflow")
    if path:
        return Path(path).resolve()

    raise RuntimeError(
        "Could not find the Codeflow executable. Set CODEFLOW_EXECUTABLE "
        "or use the bundled skill/bin/codeflow file."
    )


def read_text_arg(raw: str | None, file_path: str | None) -> str:
    if file_path:
        return Path(file_path).expanduser().read_text(encoding="utf-8")
    return raw or ""


def read_stdin_payload() -> dict[str, Any]:
    if sys.stdin.isatty():
        return {}
    raw = sys.stdin.read().strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"assistant_response": raw}
    return parsed if isinstance(parsed, dict) else {}


def detect_host_agent() -> str:
    """Best-effort detection of the coding tool running this capture.

    The host tool implements; review may be delegated to another agent, so the
    caller can still override per-event with --agent. Claude Code and Codex set
    their own session env vars, so we use those as the default actor.
    """
    for env_name in ("CODEX_THREAD_ID", "CODEX_SESSION_ID"):
        if os.environ.get(env_name, "").strip():
            return "codex"
    for env_name in (
        "CLAUDECODE_SESSION_ID",
        "CLAUDE_CODE_SESSION_ID",
        "CLAUDE_CODE_ENTRYPOINT",
        "CLAUDECODE",
        "CLAUDE_CODE",
    ):
        if os.environ.get(env_name, "").strip():
            return "claude-code"
    return ""


def default_capture_session_id(raw_session_id: str, stdin_payload: dict[str, Any]) -> str:
    explicit = str(stdin_payload.get("session_id") or raw_session_id or "").strip()
    if explicit:
        return explicit

    for env_name in (
        "CODEFLOW_SESSION_ID",
        "CODEX_THREAD_ID",
        "CODEX_SESSION_ID",
        "CLAUDECODE_SESSION_ID",
        "CLAUDE_CODE_SESSION_ID",
    ):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value

    return ""


def launch_desktop(project_root: str, session_id: str, timeout: float = DEFAULT_CAPTURE_TIMEOUT) -> None:
    log_path = Path(tempfile.gettempdir()) / "codeflow.log"
    executable = codeflow_executable()
    env = {
        **os.environ,
        "CODEFLOW_APP_ROOT": str(repo_root()),
        "CODEFLOW_PROJECT_ROOT": project_root,
    }
    if session_id:
        env["CODEFLOW_SESSION_ID"] = session_id
    cmd = [str(executable), "--project-root", project_root, "--no-build"]
    if session_id:
        cmd.extend(["--session-id", session_id])
    with log_path.open("a", encoding="utf-8") as log:
        subprocess.run(
            [str(executable), "--project-root", project_root, "--prepare-only"],
            cwd=str(repo_root()),
            env=env,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            check=True,
            timeout=timeout,
        )
        subprocess.Popen(
            cmd,
            cwd=str(repo_root()),
            env=env,
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )


def wait_for_api(timeout: float = 30.0) -> None:
    deadline = time.monotonic() + timeout
    last_error = ""
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"{API_BASE}/health", timeout=1.5) as response:
                if 200 <= response.status < 300:
                    return
        except Exception as exc:
            last_error = str(exc)
        time.sleep(0.4)
    raise RuntimeError(f"Codeflow API did not become ready: {last_error}")


def capture_timeout() -> float:
    raw = os.environ.get("CODEFLOW_CAPTURE_TIMEOUT", "").strip()
    if not raw:
        return DEFAULT_CAPTURE_TIMEOUT
    try:
        timeout = float(raw)
    except ValueError:
        return DEFAULT_CAPTURE_TIMEOUT
    return max(1.0, timeout)


def skip_capture(reason: str) -> int:
    print(f"Codeflow capture skipped: {reason}", file=sys.stderr)
    return 0


def post_capture(payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{API_BASE}/sessions/capture",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"capture failed ({exc.code}): {detail}") from exc


def post_event(payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        f"{API_BASE}/sessions/event",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"event capture failed ({exc.code}): {detail}") from exc


def stdin_or_arg(stdin_payload: dict[str, Any], key: str, arg_value: str = "") -> str:
    return str(stdin_payload.get(key) or arg_value or "")


def read_list_arg(stdin_payload: dict[str, Any], key: str, arg_values: list[str] | None) -> list[str]:
    raw = stdin_payload.get(key)
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item).strip()]
    if isinstance(raw, str) and raw.strip():
        return [item.strip() for item in raw.split(",") if item.strip()]
    return arg_values or []


def latest_group(result: dict[str, Any]) -> dict[str, Any]:
    groups = result.get("groups", [])
    latest_group_id = str(result.get("latest_group_id") or "")
    if latest_group_id:
        for group in groups:
            if isinstance(group, dict) and group.get("id") == latest_group_id:
                return group
    return groups[-1] if groups else {}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a Codex/Claude turn into Codeflow.")
    parser.add_argument("--project-root", default="")
    parser.add_argument("--session-id", default=os.environ.get("CODEFLOW_SESSION_ID", ""))
    parser.add_argument("--source", default="branch", choices=["working", "staged", "range", "branch"])
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--user-prompt", default="")
    parser.add_argument("--assistant-response", default="")
    parser.add_argument("--prompt-file", default="")
    parser.add_argument("--response-file", default="")
    parser.add_argument("--workflow-id", default=os.environ.get("CODEFLOW_WORKFLOW_ID", ""))
    parser.add_argument("--run-id", default="")
    parser.add_argument("--skill", default="")
    parser.add_argument("--skill-label", default="")
    parser.add_argument("--command-label", default="")
    parser.add_argument("--markdown-path", default="")
    parser.add_argument("--markdown-title", default="")
    parser.add_argument("--markdown-content", default="")
    parser.add_argument("--markdown-file", default="")
    parser.add_argument("--branch-name", default="")
    parser.add_argument("--event-kind", default="")
    parser.add_argument("--step-kind", default="")
    parser.add_argument("--step-id", default="")
    parser.add_argument("--step-label", default="")
    parser.add_argument("--agent", default="", help="claude-code, codex, ... who performed this step")
    parser.add_argument("--agent-label", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--detail", default="")
    parser.add_argument("--detail-file", default="")
    parser.add_argument("--status", default="completed")
    parser.add_argument("--changed-file", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stdin_payload = read_stdin_payload()
    project_root = str(
        Path(args.project_root or stdin_payload.get("project_root") or os.environ.get("PWD", "."))
        .expanduser()
        .resolve()
    )
    user_prompt = read_text_arg(args.user_prompt, args.prompt_file) or stdin_payload.get("user_prompt", "")
    assistant_response = (
        read_text_arg(args.assistant_response, args.response_file)
        or stdin_payload.get("assistant_response", "")
    )
    session_id = default_capture_session_id(args.session_id, stdin_payload)
    event_kind = stdin_or_arg(stdin_payload, "event_kind", args.event_kind) or stdin_or_arg(
        stdin_payload,
        "step_kind",
        args.step_kind,
    )

    timeout = capture_timeout()
    try:
        launch_desktop(project_root, session_id, timeout=timeout)
        wait_for_api(timeout=timeout)
    except Exception as exc:
        return skip_capture(str(exc))

    payload = {
        "project_root": project_root,
        "source": stdin_payload.get("source", args.source),
        "base_ref": stdin_payload.get("base_ref", args.base_ref) or None,
        "head_ref": stdin_payload.get("head_ref", args.head_ref) or None,
        "user_prompt": user_prompt,
        "assistant_response": assistant_response,
        "session_id": session_id or None,
    }
    if event_kind:
        markdown_content = (
            read_text_arg(None, args.markdown_file)
            or stdin_or_arg(stdin_payload, "markdown_content", args.markdown_content)
        )
        event_payload = {
            **payload,
            "workflow_id": stdin_or_arg(stdin_payload, "workflow_id", args.workflow_id),
            "run_id": stdin_or_arg(stdin_payload, "run_id", args.run_id),
            "skill": stdin_or_arg(stdin_payload, "skill", args.skill),
            "skill_label": stdin_or_arg(stdin_payload, "skill_label", args.skill_label),
            "command_label": stdin_or_arg(stdin_payload, "command_label", args.command_label),
            "markdown_path": stdin_or_arg(stdin_payload, "markdown_path", args.markdown_path),
            "markdown_title": stdin_or_arg(stdin_payload, "markdown_title", args.markdown_title),
            "markdown_content": markdown_content,
            "branch_name": stdin_or_arg(stdin_payload, "branch_name", args.branch_name),
            "step_id": stdin_or_arg(stdin_payload, "step_id", args.step_id),
            "step_kind": event_kind,
            "step_label": stdin_or_arg(stdin_payload, "step_label", args.step_label),
            "step_summary": stdin_or_arg(stdin_payload, "step_summary", args.summary),
            "step_detail": (
                read_text_arg(args.detail, args.detail_file)
                or stdin_or_arg(stdin_payload, "step_detail", "")
                or stdin_or_arg(stdin_payload, "detail", "")
            ),
            "step_status": stdin_or_arg(stdin_payload, "step_status", args.status),
            "agent": stdin_or_arg(stdin_payload, "agent", args.agent) or detect_host_agent(),
            "agent_label": stdin_or_arg(stdin_payload, "agent_label", args.agent_label),
            "files": read_list_arg(stdin_payload, "files", args.changed_file),
        }
        try:
            result = post_event(event_payload)
        except Exception as exc:
            return skip_capture(str(exc))
        latest = latest_group(result)
        runs = latest.get("workflow_runs", [])
        steps = sum(len(run.get("steps", [])) for run in runs if isinstance(run, dict))
        print(
            "Codeflow event captured "
            f"session={result.get('session_id')} group={latest.get('name')} "
            f"kind={event_kind} workflow={event_payload.get('workflow_id') or latest.get('workflow_id')} "
            f"steps={steps}"
        )
        return 0

    try:
        result = post_capture(payload)
    except Exception as exc:
        return skip_capture(str(exc))
    latest = latest_group(result)
    graph = latest.get("graph", {})
    print(
        "Codeflow captured "
        f"session={result.get('session_id')} group={latest.get('name')} "
        f"nodes={len(graph.get('nodes', []))} edges={len(graph.get('edges', []))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
