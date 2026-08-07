from __future__ import annotations

import json
import subprocess

from app.routers.changes import _event_files_scope
from app.services.sessions.store import (
    append_group,
    append_workflow_event,
    get_latest_full_graph,
    get_latest_session,
    get_latest_workflow_full_graph,
)
from app.services.sessions.insights import enrich_session_response


def _run(cmd: list[str], cwd) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True)


def test_default_state_dir_migrates_existing_history(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEFLOW_STATE_DIR", raising=False)
    monkeypatch.delenv("CODEFLOW_LIGHT_STATE_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy_dir = tmp_path / ".codeflow-light"
    legacy_dir.mkdir()
    legacy_dir.joinpath("sessions.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "latest_session_id": "legacy-thread",
                "sessions": {
                    "legacy-thread": {
                        "id": "legacy-thread",
                        "project_root": str(tmp_path),
                        "branch": "main",
                        "groups": [
                            {
                                "id": "legacy-group",
                                "name": "기존 기록",
                                "created_at": "2026-01-01T00:00:00+09:00",
                                "project_root": str(tmp_path),
                                "user_prompt": "기존 요청",
                                "assistant_response": "",
                                "graph": {"nodes": [], "edges": []},
                                "workflow_runs": [
                                    {
                                        "id": "legacy-run",
                                        "skill": "codeflow-light",
                                        "skill_label": "Codeflow Light",
                                        "status": "completed",
                                        "steps": [],
                                    }
                                ],
                            }
                        ],
                        "latest_group_id": "legacy-group",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = get_latest_session(str(tmp_path), "legacy-thread")
    stored = json.loads((tmp_path / ".codeflow" / "sessions.json").read_text())
    run = stored["sessions"]["legacy-thread"]["groups"][0]["workflow_runs"][0]

    assert result["session_id"] == "legacy-thread"
    assert run["skill"] == "codeflow"
    assert run["skill_label"] == "Codeflow"
    assert not legacy_dir.exists()


def test_state_migration_uses_custom_legacy_directory(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "custom-old-state"
    target_dir = tmp_path / "missing-parent" / "custom-new-state"
    monkeypatch.setenv("CODEFLOW_LIGHT_STATE_DIR", str(legacy_dir))
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(target_dir))
    legacy_dir.mkdir()
    legacy_dir.joinpath("sessions.json").write_text(
        json.dumps(
            {
                "latest_session_id": "custom-thread",
                "sessions": {
                    "custom-thread": {
                        "id": "custom-thread",
                        "project_root": str(tmp_path),
                        "groups": [],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    result = get_latest_session(str(tmp_path), "custom-thread")

    assert result["session_id"] == "custom-thread"
    assert target_dir.joinpath("sessions.json").exists()
    assert not legacy_dir.exists()


def test_state_migration_does_not_delete_symlinked_active_state(tmp_path, monkeypatch):
    legacy_dir = tmp_path / "state"
    legacy_dir.mkdir()
    legacy_dir.joinpath("sessions.json").write_text(
        json.dumps({"latest_session_id": None, "sessions": {}}), encoding="utf-8"
    )
    alias = tmp_path / "state-alias"
    alias.symlink_to(legacy_dir, target_is_directory=True)
    monkeypatch.setenv("CODEFLOW_LIGHT_STATE_DIR", str(legacy_dir))
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(alias))

    get_latest_session(str(tmp_path))

    assert legacy_dir.joinpath("sessions.json").exists()


def test_state_migration_merges_collisions_idempotently(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEFLOW_STATE_DIR", raising=False)
    monkeypatch.delenv("CODEFLOW_LIGHT_STATE_DIR", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    states = {}
    for directory, marker in ((".codeflow", "new"), (".codeflow-light", "old")):
        state_dir = tmp_path / directory
        state_dir.mkdir()
        session = {
            "id": "shared-thread",
            "project_root": str(tmp_path),
            "groups": [
                {
                    "id": "shared-group",
                    "name": marker,
                    "project_root": str(tmp_path),
                    "graph": {"nodes": [], "edges": []},
                }
            ],
        }
        if marker == "old":
            session["latest_group_id"] = "shared-group"
        states[directory] = {
            "schema_version": 1,
            "latest_session_id": "shared-thread",
            "sessions": {"shared-thread": session},
        }
        state_dir.joinpath("sessions.json").write_text(json.dumps(states[directory]), encoding="utf-8")

    result = get_latest_session(str(tmp_path), "shared-thread")
    assert [group["name"] for group in result["groups"]] == ["new", "old"]
    assert result["latest_group_id"] == "shared-group-legacy-1"
    assert not (tmp_path / ".codeflow-light").exists()

    legacy_dir = tmp_path / ".codeflow-light"
    legacy_dir.mkdir()
    legacy_dir.joinpath("sessions.json").write_text(
        json.dumps(states[".codeflow-light"]), encoding="utf-8"
    )
    repeated = get_latest_session(str(tmp_path), "shared-thread")

    assert [group["name"] for group in repeated["groups"]] == ["new", "old"]


def test_append_group_persists_latest_session(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
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
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
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
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
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
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
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
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
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


def test_append_workflow_event_builds_live_markdown_loop(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "branch",
        "nodes": [
            {
                "id": "file::app",
                "kind": "changed",
                "symbol_kind": "file",
                "file": "app.py",
                "status": "modified",
                "added_lines": 5,
                "removed_lines": 1,
            }
        ],
        "edges": [],
        "assistant_response": "구현 이벤트",
    }

    append_workflow_event(
        project_root=str(tmp_path),
        graph={**graph, "nodes": []},
        full_graph=graph,
        session_id="thread-events",
        workflow_id="workflow-1",
        run_id="request-md",
        user_prompt="[$markdown-branch-commit] request.md",
        skill="markdown-branch-commit",
        skill_label="Markdown Branch Commit",
        command_label="request.md",
        markdown_path="request.md",
        markdown_content="# Request\nBuild it.",
        step_kind="markdown",
        step_summary="Markdown 요청을 읽었습니다.",
    )
    result = append_workflow_event(
        project_root=str(tmp_path),
        graph=graph,
        full_graph=graph,
        session_id="thread-events",
        workflow_id="workflow-1",
        run_id="request-md",
        step_kind="implementation",
        step_summary="app.py 구현을 추가했습니다.",
    )

    group = result["groups"][0]
    run = group["workflow_runs"][0]

    assert result["session_id"] == "thread-events"
    assert result["latest_group_id"] == group["id"]
    assert group["workflow_id"] == "workflow-1"
    assert group["phase"] == "implementation"
    assert group["summary"]["review"] == []
    assert "workflow_events" not in group
    assert run["markdown_path"] == "request.md"
    assert [step["kind"] for step in run["steps"]] == ["markdown", "implementation"]
    assert run["steps"][1]["summary"] == "app.py 구현을 추가했습니다."
    assert run["steps"][1]["graph"]["nodes"][0]["file"] == "app.py"
    assert group["summary"]["workflow_step_count"] == 2
    assert "latest_full_graph" not in run
    assert get_latest_workflow_full_graph(
        str(tmp_path),
        session_id="thread-events",
        workflow_id="workflow-1",
        run_id="request-md",
    ) == graph
    assert get_latest_workflow_full_graph(
        str(tmp_path),
        session_id="thread-events",
        workflow_id="workflow-1",
        run_id="another-md",
    ) is None
    state = json.loads((tmp_path / "state" / "sessions.json").read_text())
    stored_group = state["sessions"]["thread-events"]["groups"][0]
    assert "workflow_events" in stored_group
    assert "graph" not in stored_group["workflow_events"][0]["step"]


def test_workflow_event_tracks_all_tool_pairings_and_git_agents(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "branch",
        "nodes": [],
        "edges": [],
    }
    pairings = [
        ("claude-code", "codex"),
        ("codex", "codex"),
        ("claude-code", "claude-code"),
        ("codex", "claude-code"),
    ]

    for index, (implementer, reviewer) in enumerate(pairings):
        common = {
            "project_root": str(tmp_path),
            "graph": graph,
            "session_id": f"thread-agents-{index}",
            "workflow_id": f"workflow-agents-{index}",
            "run_id": "request-md",
            "skill": "markdown-branch-commit",
        }
        append_workflow_event(
            **common,
            step_id="implementation",
            step_kind="implementation",
            agent=implementer,
        )
        result = append_workflow_event(
            **common,
            step_id="review",
            step_kind="review",
            agent=reviewer,
        )
        steps = result["groups"][0]["workflow_runs"][0]["steps"]

        assert [(step["kind"], step["agent"]) for step in steps] == [
            ("implementation", implementer),
            ("review", reviewer),
        ]
        assert [step["agent_label"] for step in steps] == [
            "Claude Code" if implementer == "claude-code" else "Codex",
            "Claude Code" if reviewer == "claude-code" else "Codex",
        ]

    append_workflow_event(
        project_root=str(tmp_path),
        graph=graph,
        session_id="thread-agents-0",
        workflow_id="workflow-agents-0",
        run_id="request-md",
        step_id="implementation",
        step_kind="implementation",
        step_summary="stable step update",
    )
    persisted_steps = get_latest_session(str(tmp_path), "thread-agents-0")["groups"][0][
        "workflow_runs"
    ][0]["steps"]
    assert persisted_steps[0]["agent"] == "claude-code"
    assert persisted_steps[0]["agent_label"] == "Claude Code"

    git_common = {
        "project_root": str(tmp_path),
        "graph": graph,
        "session_id": "thread-git-agents",
        "workflow_id": "workflow-git-agents",
        "run_id": "request-md",
        "skill": "markdown-branch-push",
    }
    result = None
    for kind, agent in [
        ("branch", "claude-code"),
        ("commit", "claude-code"),
        ("push", "codex"),
        ("merge", "codex"),
    ]:
        result = append_workflow_event(**git_common, step_kind=kind, agent=agent)

    assert result is not None
    steps = result["groups"][0]["workflow_runs"][0]["steps"]
    assert [(step["kind"], step["agent"]) for step in steps] == [
        ("branch", "claude-code"),
        ("commit", "claude-code"),
        ("push", "codex"),
        ("merge", "codex"),
    ]


def test_workflow_event_agent_label_override_and_default(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {"project_root": str(tmp_path), "source": "branch", "nodes": [], "edges": []}

    explicit = append_workflow_event(
        project_root=str(tmp_path),
        graph=graph,
        session_id="thread-agent-label",
        workflow_id="workflow-agent-label",
        run_id="request-md",
        step_id="implementation",
        step_kind="implementation",
        agent="my-tool",
        agent_label="사내 도구",
    )
    step = explicit["groups"][0]["workflow_runs"][0]["steps"][0]

    assert step["agent"] == "my-tool"
    assert step["agent_label"] == "사내 도구"

    updated = append_workflow_event(
        project_root=str(tmp_path),
        graph=graph,
        session_id="thread-agent-label",
        workflow_id="workflow-agent-label",
        run_id="request-md",
        step_id="implementation",
        step_kind="implementation",
        agent="my-tool",
    )
    updated_step = updated["groups"][0]["workflow_runs"][0]["steps"][0]

    assert updated_step["agent_label"] == "사내 도구"


def test_general_capture_skill_label_is_localized(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {"project_root": str(tmp_path), "source": "branch", "nodes": [], "edges": []}

    result = append_workflow_event(
        project_root=str(tmp_path),
        graph=graph,
        session_id="thread-general",
        workflow_id="workflow-general",
        run_id="ad-hoc",
        skill="general",
        command_label="버그 조사",
        step_kind="implementation",
        step_summary="원인을 찾고 수정했습니다.",
        agent="claude-code",
    )

    run = result["groups"][0]["workflow_runs"][0]
    assert run["skill_label"] == "General capture"


def test_general_capture_completes_on_verification(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {"project_root": str(tmp_path), "source": "branch", "nodes": [], "edges": []}
    common = {
        "project_root": str(tmp_path),
        "graph": graph,
        "session_id": "thread-general-complete",
        "workflow_id": "workflow-general-complete",
        "run_id": "ad-hoc",
        "skill": "general",
    }

    after_implementation = append_workflow_event(
        **common,
        step_kind="implementation",
        step_status="completed",
    )
    after_verification = append_workflow_event(
        **common,
        step_kind="verification",
        step_status="completed",
    )

    assert after_implementation["groups"][0]["workflow_runs"][0]["status"] == "in_progress"
    assert after_verification["groups"][0]["workflow_runs"][0]["status"] == "completed"


def test_workflow_latest_graph_uses_default_markdown_run_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "branch",
        "nodes": [{"id": "file::app", "kind": "changed", "symbol_kind": "file", "file": "app.py"}],
        "edges": [],
    }

    append_workflow_event(
        project_root=str(tmp_path),
        graph=graph,
        full_graph=graph,
        session_id="thread-default-run",
        workflow_id="workflow-default-run",
        markdown_path="requests/fix app.md",
        step_kind="implementation",
    )

    assert get_latest_workflow_full_graph(
        str(tmp_path),
        session_id="thread-default-run",
        workflow_id="workflow-default-run",
        markdown_path="requests/fix app.md",
    ) == graph


def test_workflow_event_step_graph_is_scoped_to_files(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "branch",
        "nodes": [
            {
                "id": "file::app",
                "kind": "changed",
                "symbol_kind": "file",
                "file": "app.py",
                "added_lines": 4,
                "removed_lines": 0,
            },
            {
                "id": "symbol::app::main",
                "kind": "changed",
                "symbol_kind": "function",
                "file": "app.py",
            },
            {
                "id": "file::other",
                "kind": "changed",
                "symbol_kind": "file",
                "file": "other.py",
                "added_lines": 8,
                "removed_lines": 1,
            },
        ],
        "edges": [
            {
                "id": "edge::app",
                "source": "file::app",
                "target": "symbol::app::main",
                "kind": "contains",
            },
            {
                "id": "edge::other",
                "source": "file::app",
                "target": "file::other",
                "kind": "imports",
            },
        ],
    }

    result = append_workflow_event(
        project_root=str(tmp_path),
        graph=graph,
        session_id="thread-scoped-files",
        workflow_id="workflow-scoped-files",
        run_id="request-md",
        step_kind="implementation",
        files=["app.py"],
    )

    step_graph = result["groups"][0]["workflow_runs"][0]["steps"][0]["graph"]

    assert [node["file"] for node in step_graph["nodes"]] == ["app.py", "app.py"]
    assert [edge["id"] for edge in step_graph["edges"]] == ["edge::app"]


def test_router_omitted_event_files_keeps_diff_steps_unscoped():
    assert _event_files_scope("implementation", []) is None
    assert _event_files_scope("review_fix", [" app.py "]) == ["app.py"]
    assert _event_files_scope("review", []) == []


def test_explicit_workflow_merges_repeated_file_diffs():
    first_graph = {
        "project_root": "/tmp/repo",
        "source": "branch",
        "nodes": [
            {
                "id": "file::app",
                "kind": "changed",
                "symbol_kind": "file",
                "file": "app.py",
                "added_lines": 5,
                "removed_lines": 0,
                "snippet": "+first change",
            }
        ],
        "edges": [],
    }
    second_graph = {
        "project_root": "/tmp/repo",
        "source": "branch",
        "nodes": [
            {
                "id": "file::app",
                "kind": "changed",
                "symbol_kind": "file",
                "file": "app.py",
                "added_lines": 1,
                "removed_lines": 2,
                "snippet": "-review issue\n+review fix",
            }
        ],
        "edges": [],
    }

    result = enrich_session_response({
        "session_id": "thread-merge",
        "project_root": "/tmp/repo",
        "branch": "main",
        "latest_group_id": "group-1",
        "groups": [
            {
                "id": "group-1",
                "project_root": "/tmp/repo",
                "user_prompt": "[$markdown-branch-commit] request.md",
                "assistant_response": "",
                "graph": first_graph,
                "workflow_runs": [
                    {
                        "id": "request-md",
                        "skill": "markdown-branch-commit",
                        "steps": [
                            {
                                "id": "implementation-1",
                                "kind": "implementation",
                                "summary": "초기 구현",
                                "graph": first_graph,
                            },
                            {
                                "id": "review_fix-1",
                                "kind": "review_fix",
                                "summary": "리뷰 반영",
                                "graph": second_graph,
                            },
                        ],
                    }
                ],
            }
        ],
    })

    group = result["groups"][0]

    assert group["summary"]["added_lines"] == 6
    assert group["summary"]["removed_lines"] == 2
    assert group["summary"]["changed_files"] == ["app.py"]
    assert group["graph"]["nodes"][0]["snippet"] == "+first change\n-review issue\n+review fix"


def test_explicit_workflow_aggregates_only_diff_bearing_steps():
    markdown_graph = {
        "project_root": "/tmp/repo",
        "source": "branch",
        "nodes": [
            {
                "id": "file::app",
                "kind": "changed",
                "symbol_kind": "file",
                "file": "app.py",
                "added_lines": 1,
                "removed_lines": 0,
            }
        ],
        "edges": [],
    }
    implementation_graph = {
        "project_root": "/tmp/repo",
        "source": "branch",
        "nodes": [
            {
                "id": "file::app",
                "kind": "changed",
                "symbol_kind": "file",
                "file": "app.py",
                "added_lines": 2,
                "removed_lines": 1,
            }
        ],
        "edges": [],
    }
    review_graph = {
        **implementation_graph,
        "warnings": ["no new diff since previous session group"],
    }

    result = enrich_session_response({
        "session_id": "thread-diff-only",
        "project_root": "/tmp/repo",
        "branch": "main",
        "latest_group_id": "group-1",
        "groups": [
            {
                "id": "group-1",
                "project_root": "/tmp/repo",
                "user_prompt": "[$markdown-branch-commit] request.md",
                "assistant_response": "",
                "graph": markdown_graph,
                "workflow_runs": [
                    {
                        "id": "request-md",
                        "skill": "markdown-branch-commit",
                        "steps": [
                            {"id": "markdown-1", "kind": "markdown", "graph": markdown_graph},
                            {
                                "id": "implementation-1",
                                "kind": "implementation",
                                "graph": implementation_graph,
                            },
                            {"id": "review-1", "kind": "review", "graph": review_graph},
                        ],
                    }
                ],
            }
        ],
    })

    group = result["groups"][0]

    assert group["summary"]["added_lines"] == 2
    assert group["summary"]["removed_lines"] == 1
    assert group["graph"]["warnings"] == []


def test_explicit_workflow_non_diff_steps_replace_raw_graph():
    raw_graph = {
        "project_root": "/tmp/repo",
        "source": "branch",
        "nodes": [
            {
                "id": "file::app",
                "kind": "changed",
                "symbol_kind": "file",
                "file": "app.py",
                "added_lines": 9,
                "removed_lines": 4,
            }
        ],
        "edges": [],
    }

    result = enrich_session_response({
        "session_id": "thread-review-only",
        "project_root": "/tmp/repo",
        "branch": "main",
        "latest_group_id": "group-1",
        "groups": [
            {
                "id": "group-1",
                "project_root": "/tmp/repo",
                "user_prompt": "[$markdown-branch-commit] request.md",
                "assistant_response": "",
                "graph": raw_graph,
                "workflow_runs": [
                    {
                        "id": "request-md",
                        "skill": "markdown-branch-commit",
                        "steps": [
                            {"id": "markdown-1", "kind": "markdown", "graph": raw_graph},
                            {"id": "review-1", "kind": "review", "graph": raw_graph},
                        ],
                    }
                ],
            }
        ],
    })

    group = result["groups"][0]

    assert group["summary"]["changed_files"] == []
    assert group["summary"]["added_lines"] == 0
    assert group["summary"]["removed_lines"] == 0
    assert group["graph"]["nodes"] == []


def test_explicit_workflow_phase_uses_event_order_for_repeated_loop():
    result = enrich_session_response({
        "session_id": "thread-phase",
        "project_root": "/tmp/repo",
        "branch": "main",
        "latest_group_id": "group-1",
        "groups": [
            {
                "id": "group-1",
                "project_root": "/tmp/repo",
                "user_prompt": "[$markdown-branch-commit] request.md",
                "assistant_response": "",
                "graph": {"project_root": "/tmp/repo", "source": "branch", "nodes": [], "edges": []},
                "workflow_runs": [
                    {
                        "id": "request-md",
                        "skill": "markdown-branch-commit",
                        "steps": [
                            {
                                "id": "review_fix-1",
                                "kind": "review_fix",
                                "summary": "첫 리뷰 반영",
                                "status": "completed",
                                "created_at": "2026-05-18T10:00:00+09:00",
                                "sequence": 60,
                                "event_order": 2,
                            },
                            {
                                "id": "review-2",
                                "kind": "review",
                                "summary": "두 번째 리뷰",
                                "status": "completed",
                                "created_at": "2026-05-18T10:00:00+09:00",
                                "sequence": 50,
                                "event_order": 3,
                            },
                        ],
                    }
                ],
            }
        ],
    })

    assert result["groups"][0]["phase"] == "review"


def test_markdown_branch_push_requires_push_and_merge_to_complete(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "branch",
        "nodes": [],
        "edges": [],
    }
    common = {
        "project_root": str(tmp_path),
        "graph": graph,
        "session_id": "thread-push",
        "workflow_id": "workflow-push",
        "run_id": "request-md",
        "skill": "markdown-branch-push",
    }

    after_commit = append_workflow_event(**common, step_kind="commit", step_status="completed")
    after_push = append_workflow_event(**common, step_kind="push", step_status="completed")
    after_merge = append_workflow_event(**common, step_kind="merge", step_status="completed")

    assert after_commit["groups"][0]["workflow_runs"][0]["status"] == "in_progress"
    assert after_push["groups"][0]["workflow_runs"][0]["status"] == "in_progress"
    assert after_merge["groups"][0]["workflow_runs"][0]["status"] == "completed"


def test_workflow_event_update_keeps_group_as_latest(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "branch",
        "nodes": [],
        "edges": [],
    }
    common = {
        "project_root": str(tmp_path),
        "graph": graph,
        "session_id": "thread-interleaved",
        "run_id": "request-md",
    }

    first = append_workflow_event(**common, workflow_id="workflow-one", step_kind="implementation")
    second = append_workflow_event(**common, workflow_id="workflow-two", step_kind="implementation")
    updated_first = append_workflow_event(**common, workflow_id="workflow-one", step_kind="review")
    latest = get_latest_session(str(tmp_path), "thread-interleaved")

    assert first["latest_group_id"] != second["latest_group_id"]
    assert updated_first["latest_group_id"] == first["latest_group_id"]
    assert latest["latest_group_id"] == first["latest_group_id"]


def test_repeated_review_loop_preserves_event_order(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "branch",
        "nodes": [],
        "edges": [],
    }
    common = {
        "project_root": str(tmp_path),
        "graph": graph,
        "session_id": "thread-repeat-review",
        "workflow_id": "workflow-repeat-review",
        "run_id": "request-md",
        "skill": "markdown-branch-commit",
    }

    result = None
    for kind in ["implementation", "review", "review_fix", "review", "review_fix", "verification"]:
        result = append_workflow_event(**common, step_kind=kind, step_summary=kind)

    assert result is not None
    steps = result["groups"][0]["workflow_runs"][0]["steps"]

    assert [step["kind"] for step in steps] == [
        "implementation",
        "review",
        "review_fix",
        "review",
        "review_fix",
        "verification",
    ]
    assert [step["event_order"] for step in steps] == [1, 2, 3, 4, 5, 6]


def test_missing_workflow_id_uses_unique_fallback_group(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "branch",
        "nodes": [],
        "edges": [],
    }
    common = {
        "project_root": str(tmp_path),
        "graph": graph,
        "session_id": "thread-fallback-workflow",
        "run_id": "request-md",
        "step_kind": "implementation",
    }

    append_workflow_event(**common)
    result = append_workflow_event(**common)

    workflow_ids = [group["workflow_id"] for group in result["groups"]]

    assert len(result["groups"]) == 2
    assert len(set(workflow_ids)) == 2


def test_markdown_branch_commit_completes_on_commit(tmp_path, monkeypatch):
    monkeypatch.setenv("CODEFLOW_STATE_DIR", str(tmp_path / "state"))
    graph = {
        "project_root": str(tmp_path),
        "source": "branch",
        "nodes": [],
        "edges": [],
    }

    result = append_workflow_event(
        project_root=str(tmp_path),
        graph=graph,
        session_id="thread-commit",
        workflow_id="workflow-commit",
        run_id="request-md",
        skill="markdown-branch-commit",
        step_kind="commit",
        step_status="completed",
    )

    assert result["groups"][0]["workflow_runs"][0]["status"] == "completed"


def test_cors_allows_app_protocol_without_null_origin():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    allowed = client.options(
        "/api/health",
        headers={
            "Origin": "codeflow://app",
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

    assert allowed.headers["access-control-allow-origin"] == "codeflow://app"
    assert "access-control-allow-origin" not in blocked.headers
