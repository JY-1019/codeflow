#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_BASE = "http://127.0.0.1:8019/api"


def repo_root() -> Path:
    configured = os.environ.get("CODEFLOW_LIGHT_APP_ROOT", "").strip()
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
        "Could not find Codeflow Light app root. Set CODEFLOW_LIGHT_APP_ROOT to the repository path."
    )


def frontend_dir() -> Path:
    return repo_root() / "frontend"


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


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    subprocess.run(cmd, cwd=str(cwd), env=env, check=True)


def ensure_frontend_ready() -> None:
    frontend = frontend_dir()
    if not (frontend / "node_modules" / "electron").exists():
        run(["npm", "install"], frontend)

    dist_index = frontend / "dist" / "index.html"
    if not dist_index.exists() or sources_newer_than(dist_index):
        run(["npm", "run", "build"], frontend)


def sources_newer_than(target: Path) -> bool:
    watched = [
        frontend_dir() / "src",
        frontend_dir() / "electron",
        frontend_dir() / "package.json",
        frontend_dir() / "vite.config.ts",
    ]
    target_mtime = target.stat().st_mtime
    for root in watched:
        if root.is_file() and root.stat().st_mtime > target_mtime:
            return True
        if root.is_dir():
            for path in root.rglob("*"):
                if path.is_file() and path.stat().st_mtime > target_mtime:
                    return True
    return False


def default_capture_session_id(raw_session_id: str, stdin_payload: dict[str, Any]) -> str:
    explicit = str(stdin_payload.get("session_id") or raw_session_id or "").strip()
    if explicit:
        return explicit

    for env_name in (
        "CODEFLOW_LIGHT_SESSION_ID",
        "CODEX_THREAD_ID",
        "CODEX_SESSION_ID",
        "CLAUDECODE_SESSION_ID",
        "CLAUDE_CODE_SESSION_ID",
    ):
        value = os.environ.get(env_name, "").strip()
        if value:
            return value

    return ""


def launch_desktop(project_root: str, session_id: str) -> None:
    ensure_frontend_ready()
    log_path = Path(tempfile.gettempdir()) / "codeflow-light-electron.log"
    log = log_path.open("a", encoding="utf-8")
    env = {
        **os.environ,
        "CODEFLOW_LIGHT_PROJECT_ROOT": project_root,
    }
    if session_id:
        env["CODEFLOW_LIGHT_SESSION_ID"] = session_id
    subprocess.Popen(
        ["npm", "run", "electron"],
        cwd=str(frontend_dir()),
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
    raise RuntimeError(f"Codeflow Light API did not become ready: {last_error}")


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture a Codex/Claude turn into Codeflow Light.")
    parser.add_argument("--project-root", default="")
    parser.add_argument("--session-id", default=os.environ.get("CODEFLOW_LIGHT_SESSION_ID", ""))
    parser.add_argument("--source", default="branch", choices=["working", "staged", "range", "branch"])
    parser.add_argument("--base-ref", default="")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--user-prompt", default="")
    parser.add_argument("--assistant-response", default="")
    parser.add_argument("--prompt-file", default="")
    parser.add_argument("--response-file", default="")
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

    launch_desktop(project_root, session_id)
    wait_for_api()

    payload = {
        "project_root": project_root,
        "source": stdin_payload.get("source", args.source),
        "base_ref": stdin_payload.get("base_ref", args.base_ref) or None,
        "head_ref": stdin_payload.get("head_ref", args.head_ref) or None,
        "user_prompt": user_prompt,
        "assistant_response": assistant_response,
        "session_id": session_id or None,
    }
    result = post_capture(payload)
    groups = result.get("groups", [])
    latest = groups[-1] if groups else {}
    graph = latest.get("graph", {})
    print(
        "Codeflow Light captured "
        f"session={result.get('session_id')} group={latest.get('name')} "
        f"nodes={len(graph.get('nodes', []))} edges={len(graph.get('edges', []))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
