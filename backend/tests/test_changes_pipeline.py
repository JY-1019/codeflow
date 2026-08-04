"""Smoke tests for the changes pipeline without needing an LLM key."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.services.changes import graph_builder
from app.services.changes.git_diff import GitDiffResult, collect_diff
from app.services.changes.graph_builder import _extract_js_imports, build_graph
from app.services.changes.symbol_extractor import extract_symbols


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True)


def test_extract_python_symbols():
    code = (
        "def foo():\n"
        "    return 1\n"
        "\n"
        "class Bar:\n"
        "    def baz(self):\n"
        "        return foo()\n"
    )
    spans = extract_symbols(code, "python")
    names = {(s.name, s.kind) for s in spans}
    assert ("foo", "function") in names
    assert ("Bar", "class") in names
    assert ("baz", "method") in names


def test_collect_diff_and_build_graph(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    file_py = repo / "lib.py"
    file_py.write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    _run(["git", "add", "lib.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    file_py.write_text(
        "def hello():\n"
        "    return 'hi, world'\n"
        "\n"
        "def goodbye():\n"
        "    return hello()\n",
        encoding="utf-8",
    )

    diff = collect_diff(str(repo), source="working")
    file_change = next(f for f in diff.files if f.path == "lib.py")
    assert any(line.kind == "context" and "def hello" in line.text for hunk in file_change.hunks for line in hunk.lines)

    graph = build_graph(diff)
    assert graph.nodes, "expected at least one node"
    labels = {n.label for n in graph.nodes}
    assert "lib.py" in labels
    file_node = next(node for node in graph.nodes if node.label == "lib.py")
    assert "\n  def hello():" in file_node.snippet
    # symbol-level node for the new function should be present
    assert "goodbye" in labels or "hello" in labels

    # contains edge from file to a symbol
    assert any(e.kind == "contains" for e in graph.edges)


def test_collect_branch_diff_includes_worktree(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    file_py = repo / "lib.py"
    file_py.write_text("value = 1\n", encoding="utf-8")
    _run(["git", "add", "lib.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    file_py.write_text("value = 2\n", encoding="utf-8")

    diff = collect_diff(str(repo), source="branch")
    assert diff.source == "branch"
    assert diff.base_ref == "main"
    assert any(f.path == "lib.py" for f in diff.files)


def test_collect_branch_diff_prefers_main_over_feature_upstream(tmp_path: Path):
    repo = tmp_path / "repo"
    remote = tmp_path / "remote.git"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "init", "-q", "--bare", str(remote)], tmp_path)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)
    _run(["git", "remote", "add", "origin", str(remote)], repo)

    file_py = repo / "lib.py"
    file_py.write_text("value = 1\n", encoding="utf-8")
    _run(["git", "add", "lib.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)
    _run(["git", "push", "-u", "origin", "main"], repo)
    _run(["git", "checkout", "-q", "-b", "feature/session-flow"], repo)

    file_py.write_text("value = 2\n", encoding="utf-8")
    _run(["git", "add", "lib.py"], repo)
    _run(["git", "commit", "-q", "-m", "feature change"], repo)
    _run(["git", "push", "-u", "origin", "feature/session-flow"], repo)

    diff = collect_diff(str(repo), source="branch")

    assert diff.base_ref == "origin/main"
    assert any(f.path == "lib.py" for f in diff.files)


def test_collect_branch_diff_honors_explicit_head_ref(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    (repo / "lib.py").write_text("value = 1\n", encoding="utf-8")
    _run(["git", "add", "lib.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)
    _run(["git", "checkout", "-q", "-b", "feature/explicit-head"], repo)
    (repo / "lib.py").write_text("value = 2\n", encoding="utf-8")
    _run(["git", "add", "lib.py"], repo)
    _run(["git", "commit", "-q", "-m", "feature change"], repo)

    _run(["git", "checkout", "-q", "main"], repo)
    (repo / "worktree_only.py").write_text("value = 99\n", encoding="utf-8")

    diff = collect_diff(
        str(repo),
        source="branch",
        base_ref="main",
        head_ref="feature/explicit-head",
    )

    assert diff.head_ref == "feature/explicit-head"
    assert {file.path for file in diff.files} == {"lib.py"}


def test_build_graph_skips_repo_import_scan_when_no_files_changed(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()

    def fail_repo_scan(_project_root: Path):
        raise AssertionError("repo-wide import scan should not run for an empty diff")

    monkeypatch.setattr(graph_builder, "_repo_code_files", fail_repo_scan)

    graph = build_graph(
        GitDiffResult(
            source="branch",
            base_ref="main",
            head_ref="HEAD",
            project_root=str(repo),
            files=[],
            raw_patch="",
        )
    )

    assert graph.nodes == []
    assert graph.edges == []


def test_changes_latest_defaults_to_branch_diff(tmp_path: Path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    (repo / "lib.py").write_text("value = 1\n", encoding="utf-8")
    _run(["git", "add", "lib.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)
    _run(["git", "checkout", "-q", "-b", "feature/latest-branch"], repo)
    (repo / "lib.py").write_text("value = 2\n", encoding="utf-8")
    _run(["git", "add", "lib.py"], repo)
    _run(["git", "commit", "-q", "-m", "feature change"], repo)

    monkeypatch.setenv("CODEFLOW_PROJECT_ROOT", str(repo))

    from app.routers import changes as changes_router
    from fastapi.testclient import TestClient
    from main import app

    changes_router._LATEST_RESULTS.clear()
    response = TestClient(app).get("/api/changes/latest")
    changes_router._LATEST_RESULTS.clear()

    body = response.json()
    assert response.status_code == 200
    assert body["source"] == "branch"
    assert any(node["file"] == "lib.py" for node in body["nodes"])


def test_changes_latest_is_scoped_to_requested_project(tmp_path: Path):
    repo_one = tmp_path / "repo-one"
    repo_two = tmp_path / "repo-two"

    for repo, filename, initial, updated in (
        (repo_one, "one.py", "value = 1\n", "value = 2\n"),
        (repo_two, "two.py", "name = 'old'\n", "name = 'new'\n"),
    ):
        repo.mkdir()
        _run(["git", "init", "-q", "-b", "main"], repo)
        _run(["git", "config", "user.email", "test@example.com"], repo)
        _run(["git", "config", "user.name", "Test"], repo)
        (repo / filename).write_text(initial, encoding="utf-8")
        _run(["git", "add", filename], repo)
        _run(["git", "commit", "-q", "-m", "initial"], repo)
        _run(["git", "checkout", "-q", "-b", "feature/change"], repo)
        (repo / filename).write_text(updated, encoding="utf-8")
        _run(["git", "add", filename], repo)
        _run(["git", "commit", "-q", "-m", "feature change"], repo)

    from app.routers import changes as changes_router
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    changes_router._LATEST_RESULTS.clear()
    first_response = client.post(
        "/api/changes",
        json={"project_root": str(repo_one), "source": "branch"},
    )
    latest_response = client.get(
        "/api/changes/latest",
        params={"project_root": str(repo_two)},
    )
    changes_router._LATEST_RESULTS.clear()

    assert first_response.status_code == 200
    assert latest_response.status_code == 200
    body = latest_response.json()
    assert body["project_root"] == str(repo_two.resolve())
    assert any(node["file"] == "two.py" for node in body["nodes"])
    assert not any(node["file"] == "one.py" for node in body["nodes"])


def test_collect_diff_includes_untracked_file_contents(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    (repo / "new_feature.py").write_text(
        "def new_feature():\n"
        "    return 'visible in docs'\n",
        encoding="utf-8",
    )

    diff = collect_diff(str(repo), source="working")
    change = next(file for file in diff.files if file.path == "new_feature.py")

    assert change.status == "added"
    assert sum(len(hunk.added_lines) for hunk in change.hunks) == 2
    assert "visible in docs" in change.hunks[0].added_lines[1][1]


def test_collect_diff_skips_untracked_symlink_targets(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)
    (repo / "README.md").write_text("initial\n", encoding="utf-8")
    _run(["git", "add", "README.md"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    secret = tmp_path / "secret.py"
    secret.write_text("TOKEN = 'do-not-leak'\n", encoding="utf-8")
    link = repo / "leaked.py"
    try:
        link.symlink_to(secret)
    except OSError:
        pytest.skip("symlinks are not supported on this filesystem")

    diff = collect_diff(str(repo), source="working")
    change = next(file for file in diff.files if file.path == "leaked.py")
    graph = build_graph(diff)
    snippets = "\n".join(node.snippet for node in graph.nodes)

    assert change.status == "added"
    assert change.hunks[0].added_lines == [(1, "symlink target omitted")]
    assert "do-not-leak" not in snippets
    assert any("untracked symlink skipped" in warning for warning in diff.warnings)


def test_extract_js_imports_keeps_side_effect_imports_separate():
    refs = _extract_js_imports(
        "import './setup';\n"
        "import { render } from './render';\n"
    )

    assert [(ref.module, ref.line) for ref in refs] == [
        ("./setup", 1),
        ("./render", 2),
    ]


def test_build_graph_adds_project_import_edges(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    src = repo / "src"
    src.mkdir()
    (src / "util.ts").write_text(
        "export function formatName(name: string) {\n"
        "  return name.trim();\n"
        "}\n",
        encoding="utf-8",
    )
    app_ts = src / "app.ts"
    app_ts.write_text(
        "import { formatName } from './util';\n"
        "\n"
        "export function render(name: string) {\n"
        "  return formatName(name);\n"
        "}\n",
        encoding="utf-8",
    )
    _run(["git", "add", "src/app.ts", "src/util.ts"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    app_ts.write_text(
        "import { formatName } from './util';\n"
        "\n"
        "export function render(name: string) {\n"
        "  return `Hello ${formatName(name)}`;\n"
        "}\n",
        encoding="utf-8",
    )

    graph = build_graph(collect_diff(str(repo), source="working"))
    files = {node.file for node in graph.nodes}

    assert "src/app.ts" in files
    assert "src/util.ts" in files
    assert any(
        edge.kind == "imports"
        and graph_node_file(graph, edge.source) == "src/app.ts"
        and graph_node_file(graph, edge.target) == "src/util.ts"
        for edge in graph.edges
    )


def test_build_graph_adds_import_users_for_changed_files(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    src = repo / "src"
    src.mkdir()
    util_ts = src / "util.ts"
    util_ts.write_text(
        "export function formatName(name: string) {\n"
        "  return name.trim();\n"
        "}\n",
        encoding="utf-8",
    )
    (src / "app.ts").write_text(
        "import { formatName } from './util';\n"
        "\n"
        "export function render(name: string) {\n"
        "  return formatName(name);\n"
        "}\n",
        encoding="utf-8",
    )
    _run(["git", "add", "src/app.ts", "src/util.ts"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    util_ts.write_text(
        "export function formatName(name: string) {\n"
        "  return name.trim().toUpperCase();\n"
        "}\n",
        encoding="utf-8",
    )

    graph = build_graph(collect_diff(str(repo), source="working"))

    assert any(node.file == "src/app.ts" and node.kind == "affected" for node in graph.nodes)
    assert any(
        edge.kind == "imports"
        and graph_node_file(graph, edge.source) == "src/app.ts"
        and graph_node_file(graph, edge.target) == "src/util.ts"
        for edge in graph.edges
    )


def test_build_graph_resolves_frontend_src_alias_imports(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    frontend_src = repo / "frontend" / "src"
    (frontend_src / "components").mkdir(parents=True)
    (frontend_src / "types").mkdir(parents=True)
    types_file = frontend_src / "types" / "changes.ts"
    component_file = frontend_src / "components" / "SessionFlow.tsx"
    types_file.write_text("export interface ChangeGroup { id: string }\n", encoding="utf-8")
    component_file.write_text(
        "import type { ChangeGroup } from '@/types/changes';\n"
        "\n"
        "export function label(group: ChangeGroup) {\n"
        "  return group.id;\n"
        "}\n",
        encoding="utf-8",
    )
    _run(
        ["git", "add", "frontend/src/types/changes.ts", "frontend/src/components/SessionFlow.tsx"],
        repo,
    )
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    component_file.write_text(
        "import type { ChangeGroup } from '@/types/changes';\n"
        "\n"
        "export function label(group: ChangeGroup) {\n"
        "  return `step-${group.id}`;\n"
        "}\n",
        encoding="utf-8",
    )

    graph = build_graph(collect_diff(str(repo), source="working"))

    assert any(
        edge.kind == "imports"
        and graph_node_file(graph, edge.source) == "frontend/src/components/SessionFlow.tsx"
        and graph_node_file(graph, edge.target) == "frontend/src/types/changes.ts"
        for edge in graph.edges
    )


def test_build_graph_resolves_python_imports_from_backend_package_root(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)

    service_dir = repo / "backend" / "app" / "services" / "changes"
    tests_dir = repo / "backend" / "tests"
    service_dir.mkdir(parents=True)
    tests_dir.mkdir(parents=True)
    (service_dir / "__init__.py").write_text("", encoding="utf-8")
    service_file = service_dir / "default_docs.py"
    test_file = tests_dir / "test_default_docs.py"
    service_file.write_text(
        "def fill_default_docs():\n"
        "    return 'old docs'\n",
        encoding="utf-8",
    )
    test_file.write_text(
        "from app.services.changes.default_docs import fill_default_docs\n"
        "\n"
        "def test_docs():\n"
        "    assert fill_default_docs()\n",
        encoding="utf-8",
    )
    _run(
        [
            "git",
            "add",
            "backend/app/services/changes/__init__.py",
            "backend/app/services/changes/default_docs.py",
            "backend/tests/test_default_docs.py",
        ],
        repo,
    )
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    service_file.write_text(
        "def fill_default_docs():\n"
        "    return 'better docs'\n",
        encoding="utf-8",
    )

    graph = build_graph(collect_diff(str(repo), source="working"))

    assert any(node.file == "backend/tests/test_default_docs.py" and node.kind == "affected" for node in graph.nodes)
    assert any(
        edge.kind == "imports"
        and graph_node_file(graph, edge.source) == "backend/tests/test_default_docs.py"
        and graph_node_file(graph, edge.target) == "backend/app/services/changes/default_docs.py"
        for edge in graph.edges
    )


def graph_node_file(graph, node_id: str) -> str | None:
    node = next((item for item in graph.nodes if item.id == node_id), None)
    return node.file if node else None
