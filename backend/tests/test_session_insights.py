from __future__ import annotations

from app.services.sessions.insights import enrich_session_response


def test_enrich_session_response_adds_phase_and_session_summary():
    response = {
        "session_id": "thread-1",
        "project_root": "/tmp/repo",
        "branch": "main",
        "latest_group_id": "g1",
        "groups": [
            {
                "id": "g1",
                "name": "2026-05-18 10:00:00",
                "created_at": "2026-05-18T10:00:00+09:00",
                "project_root": "/tmp/repo",
                "user_prompt": "세션 흐름 시각화를 구현해줘",
                "assistant_response": "구현: `SessionFlow`가 구현/리뷰 단계를 보여줍니다.\n검증: typecheck를 실행했습니다.",
                "graph": {
                    "nodes": [
                        {
                            "id": "file::frontend",
                            "kind": "changed",
                            "symbol_kind": "file",
                            "file": "frontend/src/components/SessionFlow.tsx",
                            "status": "modified",
                            "added_lines": 20,
                            "removed_lines": 4,
                        }
                    ],
                    "edges": [],
                },
            }
        ],
    }

    enriched = enrich_session_response(response)
    group = enriched["groups"][0]

    assert group["phase"] == "implementation"
    assert group["summary"]["changed_files"] == ["frontend/src/components/SessionFlow.tsx"]
    assert group["summary"]["added_lines"] == 20
    assert "구현: `SessionFlow`가 구현/리뷰 단계를 보여줍니다." in group["summary"]["implementation"]
    assert enriched["summary"]["total_groups"] == 1
    assert enriched["summary"]["phase_counts"]["implementation"] == 1
    assert any(item["label"] == "리뷰 루프" for item in enriched["summary"]["technical_considerations"])


def test_enrich_session_response_filters_noisy_codex_review_output():
    response = {
        "session_id": "thread-1",
        "project_root": "/tmp/repo",
        "branch": "main",
        "latest_group_id": "g1",
        "groups": [
            {
                "id": "g1",
                "name": "2026-05-18 10:00:00",
                "created_at": "2026-05-18T10:00:00+09:00",
                "project_root": "/tmp/repo",
                "user_prompt": "uncommitted review",
                "assistant_response": (
                    "[output truncated]\n"
                    "sed -n '1,360p' frontend/src/flow/utils/positions.ts\" "
                    "in /Users/a86466/workspace/codeflow\n"
                    " succeeded in 0ms:\n"
                    "import type { Node } from '@xyflow/react';\n"
                    "const noisy = true;\n"
                    "2026-05-18T01:43:07.092330Z  WARN codex_protocol::openai_models: "
                    "Model personality requested but model_messages is missing\n"
                    "Findings\n"
                    "- [P1] 실제 리뷰 finding은 유지합니다.\n"
                ),
                "graph": {
                    "nodes": [],
                    "edges": [],
                    "assistant_response": "",
                    "narrative": "",
                },
            }
        ],
    }

    enriched = enrich_session_response(response)
    assistant_response = enriched["groups"][0]["assistant_response"]

    assert "Findings" in assistant_response
    assert "실제 리뷰 finding" in assistant_response
    assert "output truncated" not in assistant_response
    assert "codex_protocol" not in assistant_response
    assert "const noisy" not in assistant_response


def test_enrich_session_response_adds_markdown_workflow_runs():
    response = {
        "session_id": "thread-1",
        "project_root": "/tmp/repo",
        "branch": "main",
        "latest_group_id": "g1",
        "groups": [
            {
                "id": "g1",
                "name": "2026-05-18 10:00:00",
                "created_at": "2026-05-18T10:00:00+09:00",
                "project_root": "/tmp/repo",
                "user_prompt": (
                    "[$markdown-branch-push](/Users/me/.codex/skills/markdown-branch-push/SKILL.md)\n"
                    "```markdown\n"
                    "# Flowchart view\n"
                    "Show Markdown command review loops.\n"
                    "```\n"
                ),
                "assistant_response": (
                    "구현: `SessionFlow`가 Markdown 명령과 리뷰 루프를 보여줍니다.\n"
                    "리뷰: codex review에서 actionable finding이 없었습니다.\n"
                    "검증: npm run typecheck를 실행했습니다.\n"
                    "커밋하지 않았고 push하지 않았습니다."
                ),
                "graph": {
                    "nodes": [
                        {
                            "id": "file::frontend",
                            "kind": "changed",
                            "symbol_kind": "file",
                            "file": "frontend/src/components/SessionFlow.tsx",
                            "status": "modified",
                            "added_lines": 42,
                            "removed_lines": 7,
                        }
                    ],
                    "edges": [],
                },
            }
        ],
    }

    enriched = enrich_session_response(response)
    group = enriched["groups"][0]
    runs = group["workflow_runs"]

    assert len(runs) == 1
    assert runs[0]["skill"] == "markdown-branch-push"
    assert runs[0]["markdown_title"] == "Flowchart view"
    assert "Show Markdown command review loops." in runs[0]["markdown_content"]
    assert runs[0]["markdown_path"] == ""
    assert [step["kind"] for step in runs[0]["steps"]][-2:] == ["push", "merge"]
    assert any(step["kind"] == "review" and step["status"] == "completed" for step in runs[0]["steps"])
    assert any(step["kind"] == "verification" and step["status"] == "completed" for step in runs[0]["steps"])
    assert group["summary"]["workflow_run_count"] == 1
    assert enriched["summary"]["workflow_step_count"] == len(runs[0]["steps"])


def test_enrich_session_response_does_not_treat_plain_markdown_as_skill_workflow():
    response = {
        "session_id": "thread-1",
        "project_root": "/tmp/repo",
        "branch": "main",
        "latest_group_id": "g1",
        "groups": [
            {
                "id": "g1",
                "name": "2026-05-18 10:00:00",
                "created_at": "2026-05-18T10:00:00+09:00",
                "project_root": "/tmp/repo",
                "user_prompt": "README.md 문구를 다듬어줘",
                "assistant_response": "구현: `README.md` 설명을 수정했습니다.",
                "graph": {
                    "nodes": [
                        {
                            "id": "file::readme",
                            "kind": "changed",
                            "symbol_kind": "file",
                            "file": "README.md",
                            "status": "modified",
                            "added_lines": 2,
                            "removed_lines": 1,
                        }
                    ],
                    "edges": [],
                },
            }
        ],
    }

    enriched = enrich_session_response(response)
    group = enriched["groups"][0]

    assert group["workflow_runs"] == []
    assert group["summary"]["workflow_run_count"] == 0


def test_enrich_session_response_does_not_infer_workflow_from_response_skill_mentions():
    response = {
        "session_id": "thread-1",
        "project_root": "/tmp/repo",
        "branch": "main",
        "latest_group_id": "g1",
        "groups": [
            {
                "id": "g1",
                "name": "2026-05-18 10:00:00",
                "created_at": "2026-05-18T10:00:00+09:00",
                "project_root": "/tmp/repo",
                "user_prompt": "README.md에 skill 설명을 추가해줘",
                "assistant_response": (
                    "구현: README에 markdown-branch-push와 "
                    "markdown-branch-commit 설명을 추가했습니다."
                ),
                "graph": {
                    "nodes": [
                        {
                            "id": "file::readme",
                            "kind": "changed",
                            "symbol_kind": "file",
                            "file": "README.md",
                            "status": "modified",
                            "added_lines": 4,
                            "removed_lines": 1,
                        }
                    ],
                    "edges": [],
                },
            }
        ],
    }

    enriched = enrich_session_response(response)
    group = enriched["groups"][0]

    assert group["workflow_runs"] == []
    assert group["summary"]["workflow_run_count"] == 0


def test_markdown_workflow_status_uses_response_not_skill_instructions():
    response = {
        "session_id": "thread-1",
        "project_root": "/tmp/repo",
        "branch": "main",
        "latest_group_id": "g1",
        "groups": [
            {
                "id": "g1",
                "name": "2026-05-18 10:00:00",
                "created_at": "2026-05-18T10:00:00+09:00",
                "project_root": "/tmp/repo",
                "user_prompt": (
                    "[$markdown-branch-commit](/Users/me/.codex/skills/markdown-branch-commit/SKILL.md)\n"
                    "Run /review before tests and commit each Markdown file.\n"
                    "```markdown\n"
                    "# Improve session UI\n"
                    "Show the review loop clearly.\n"
                    "```\n"
                ),
                "assistant_response": "구현: 세션 UI를 리뷰 루프 중심으로 정리했습니다.",
                "graph": {
                    "nodes": [
                        {
                            "id": "file::page",
                            "kind": "changed",
                            "symbol_kind": "file",
                            "file": "frontend/src/pages/ChangePage.tsx",
                            "status": "modified",
                            "added_lines": 30,
                            "removed_lines": 5,
                        }
                    ],
                    "edges": [],
                },
            }
        ],
    }

    enriched = enrich_session_response(response)
    steps = enriched["groups"][0]["workflow_runs"][0]["steps"]
    statuses = {step["kind"]: step["status"] for step in steps}
    summaries = {step["kind"]: step["summary"] for step in steps}

    assert statuses["implementation"] == "completed"
    assert statuses["review"] == "pending"
    assert statuses["commit"] == "pending"
    assert summaries["implementation"] == "구현: 세션 UI를 리뷰 루프 중심으로 정리했습니다."
    assert "Show the review loop clearly" not in summaries["implementation"]
