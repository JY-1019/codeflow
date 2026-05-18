from __future__ import annotations

import subprocess

from app.services.sessions.store import append_group, get_latest_full_graph, get_latest_session


def _run(cmd: list[str], cwd) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True)


def test_append_group_persists_latest_session(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_LIGHT_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "working",
        "nodes": [],
        "edges": [],
        "assistant_response": "수정 설명",
    }

    result = append_group(
        project_root=str(tmp_path),
        graph=graph,
        user_prompt="이 파일 고쳐줘",
        session_id="test-session",
    )

    assert result["session_id"] == "test-session"
    assert result["latest_group_id"] == result["groups"][0]["id"]
    assert result["groups"][0]["name"]
    assert result["groups"][0]["user_prompt"] == "이 파일 고쳐줘"

    latest = get_latest_session(str(tmp_path))
    assert latest["session_id"] == "test-session"
    assert latest["groups"][0]["graph"]["assistant_response"] == "수정 설명"


def test_latest_session_can_be_filtered_by_session_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_LIGHT_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "working",
        "nodes": [],
        "edges": [],
    }

    append_group(
        project_root=str(tmp_path),
        graph={**graph, "assistant_response": "첫 번째 대화"},
        user_prompt="첫 번째",
        session_id="thread-one",
    )
    append_group(
        project_root=str(tmp_path),
        graph={**graph, "assistant_response": "두 번째 대화"},
        user_prompt="두 번째",
        session_id="thread-two",
    )

    first = get_latest_session(str(tmp_path), "thread-one")
    missing = get_latest_session(str(tmp_path), "thread-missing")

    assert first["session_id"] == "thread-one"
    assert len(first["groups"]) == 1
    assert first["groups"][0]["assistant_response"] == "첫 번째 대화"
    assert missing["session_id"] == "thread-missing"
    assert missing["groups"] == []


def test_latest_session_project_filter_does_not_return_other_project(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_LIGHT_STATE_DIR", str(tmp_path / "state"))
    first_project = tmp_path / "repo-one"
    second_project = tmp_path / "repo-two"
    first_project.mkdir()
    second_project.mkdir()
    graph = {"source": "working", "nodes": [], "edges": []}

    append_group(
        project_root=str(first_project),
        graph={**graph, "project_root": str(first_project)},
        user_prompt="첫 번째",
        session_id="thread-one",
    )

    latest = get_latest_session(str(second_project))

    assert latest["session_id"] is None
    assert latest["project_root"] == str(second_project)
    assert latest["groups"] == []


def test_missing_explicit_session_id_has_no_previous_full_graph(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_LIGHT_STATE_DIR", str(tmp_path / "state"))
    project = tmp_path / "repo"
    project.mkdir()
    graph = {
        "project_root": str(project),
        "source": "working",
        "nodes": [{"id": "file::a", "file": "a.py"}],
        "edges": [],
    }

    append_group(
        project_root=str(project),
        graph=graph,
        full_graph=graph,
        user_prompt="첫 번째",
        session_id="thread-one",
    )

    assert get_latest_full_graph(str(project), "new-thread") is None


def test_sessions_latest_normalizes_subdirectory_project_root(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_LIGHT_STATE_DIR", str(tmp_path / "state"))
    repo = tmp_path / "repo"
    subdir = repo / "frontend"
    subdir.mkdir(parents=True)
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    graph = {
        "project_root": str(repo),
        "source": "working",
        "nodes": [],
        "edges": [],
        "assistant_response": "서브디렉터리 capture",
    }
    append_group(
        project_root=str(repo),
        graph=graph,
        user_prompt="하위 폴더에서 실행",
        session_id="thread-subdir",
    )

    from fastapi.testclient import TestClient
    from main import app

    response = TestClient(app).get("/api/sessions/latest", params={"project_root": str(subdir)})

    assert response.status_code == 200
    assert response.json()["session_id"] == "thread-subdir"


def test_cors_allows_app_protocol_without_null_origin():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    allowed = client.options(
        "/api/health",
        headers={
            "Origin": "codeflow-light://app",
            "Access-Control-Request-Method": "GET",
        },
    )
    blocked = client.options(
        "/api/health",
        headers={
            "Origin": "null",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert allowed.headers["access-control-allow-origin"] == "codeflow-light://app"
    assert "access-control-allow-origin" not in blocked.headers
