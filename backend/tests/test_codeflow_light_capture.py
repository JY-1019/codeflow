from __future__ import annotations

import importlib.util
from pathlib import Path


HOST_AGENT_ENV_VARS = (
    "CLAUDECODE_SESSION_ID",
    "CLAUDE_CODE_SESSION_ID",
    "CLAUDE_CODE_ENTRYPOINT",
    "CLAUDECODE",
    "CLAUDE_CODE",
    "CODEX_THREAD_ID",
    "CODEX_SESSION_ID",
)


def _capture_module():
    path = Path(__file__).resolve().parents[2] / "skill" / "scripts" / "codeflow_light_capture.py"
    spec = importlib.util.spec_from_file_location("codeflow_light_capture", path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_detect_host_agent_ignores_codex_home_without_session(monkeypatch):
    capture = _capture_module()
    for env_name in HOST_AGENT_ENV_VARS:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("CODEX_HOME", "/tmp/codex-home")

    assert capture.detect_host_agent() == ""


def test_detect_host_agent_uses_session_specific_env(monkeypatch):
    capture = _capture_module()
    for env_name in HOST_AGENT_ENV_VARS:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("CODEX_THREAD_ID", "thread-123")

    assert capture.detect_host_agent() == "codex"


def test_detect_host_agent_prefers_codex_when_claude_env_is_inherited(monkeypatch):
    capture = _capture_module()
    for env_name in HOST_AGENT_ENV_VARS:
        monkeypatch.delenv(env_name, raising=False)
    monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", "claude-session")
    monkeypatch.setenv("CODEX_SESSION_ID", "codex-session")

    assert capture.detect_host_agent() == "codex"
