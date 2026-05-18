from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.changes.git_diff import collect_diff
from app.services.changes.graph_builder import build_graph
from app.services.changes.session_delta import (
    filter_graph_to_session_delta,
    serialized_graph_snapshot,
)


def _run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True, capture_output=True)


def _init_repo(repo: Path) -> None:
    repo.mkdir()
    _run(["git", "init", "-q", "-b", "main"], repo)
    _run(["git", "config", "user.email", "test@example.com"], repo)
    _run(["git", "config", "user.name", "Test"], repo)


def graph_node_file(graph, node_id: str) -> str | None:
    node = next((item for item in graph.nodes if item.id == node_id), None)
    return node.file if node else None


def test_session_delta_keeps_only_new_file_since_previous_capture(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "a.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("value = 10\n", encoding="utf-8")
    _run(["git", "add", "a.py", "b.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    (repo / "a.py").write_text("value = 2\n", encoding="utf-8")
    previous = serialized_graph_snapshot(build_graph(collect_diff(str(repo), source="working")))

    (repo / "b.py").write_text("value = 20\n", encoding="utf-8")
    graph = build_graph(collect_diff(str(repo), source="working"))
    filter_graph_to_session_delta(graph, previous)

    changed_files = {node.file for node in graph.nodes if node.kind == "changed"}
    assert "b.py" in changed_files
    assert "a.py" not in changed_files


def test_session_delta_removes_previously_captured_snippet_lines(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    file_py = repo / "settings.py"
    file_py.write_text("alpha = 1\n", encoding="utf-8")
    _run(["git", "add", "settings.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    file_py.write_text("alpha = 2\n", encoding="utf-8")
    previous = serialized_graph_snapshot(build_graph(collect_diff(str(repo), source="working")))

    file_py.write_text("alpha = 2\nbeta = 3\n", encoding="utf-8")
    graph = build_graph(collect_diff(str(repo), source="working"))
    filter_graph_to_session_delta(graph, previous)

    file_node = next(node for node in graph.nodes if node.file == "settings.py")
    assert "beta = 3" in file_node.snippet
    assert "alpha = 2" not in file_node.snippet
    assert "alpha = 1" not in file_node.snippet


def test_session_delta_preserves_removed_side_of_new_replacement(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    file_py = repo / "settings.py"
    file_py.write_text("alpha = 1\n", encoding="utf-8")
    _run(["git", "add", "settings.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    file_py.write_text("alpha = 2\n", encoding="utf-8")
    previous = serialized_graph_snapshot(build_graph(collect_diff(str(repo), source="working")))

    file_py.write_text("alpha = 3\n", encoding="utf-8")
    graph = build_graph(collect_diff(str(repo), source="working"))
    filter_graph_to_session_delta(graph, previous)

    file_node = next(node for node in graph.nodes if node.file == "settings.py")
    assert "- alpha = 2" in file_node.snippet
    assert "+ alpha = 3" in file_node.snippet
    assert "- alpha = 1" not in file_node.snippet


def test_session_delta_ignores_review_only_file_mentions(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "a.py").write_text("value = 1\n", encoding="utf-8")
    _run(["git", "add", "a.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    (repo / "a.py").write_text("value = 2\n", encoding="utf-8")
    previous = serialized_graph_snapshot(build_graph(collect_diff(str(repo), source="working")))
    graph = build_graph(collect_diff(str(repo), source="working"))
    filter_graph_to_session_delta(graph, previous, "리뷰 결과 `a.py`는 추가 수정 없이 괜찮습니다.")

    assert graph.nodes == []
    assert graph.edges == []
    assert "no new diff" in graph.warnings[-1]


def test_session_delta_mentions_do_not_hide_new_diff_files(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "a.py").write_text("value = 1\n", encoding="utf-8")
    (repo / "b.py").write_text("value = 10\n", encoding="utf-8")
    _run(["git", "add", "a.py", "b.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    (repo / "a.py").write_text("value = 2\n", encoding="utf-8")
    previous = serialized_graph_snapshot(build_graph(collect_diff(str(repo), source="working")))

    (repo / "b.py").write_text("value = 20\n", encoding="utf-8")
    graph = build_graph(collect_diff(str(repo), source="working"))
    filter_graph_to_session_delta(graph, previous, "마지막 응답에서는 `a.py`도 설명했습니다.")

    changed_files = {node.file for node in graph.nodes if node.kind == "changed"}
    assert changed_files == {"b.py"}


def test_session_delta_removes_affected_and_context_files(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    src = repo / "src"
    src.mkdir()
    (src / "util.ts").write_text(
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

    (src / "util.ts").write_text(
        "export function formatName(name: string) {\n"
        "  return name.trim().toUpperCase();\n"
        "}\n",
        encoding="utf-8",
    )

    graph = build_graph(collect_diff(str(repo), source="working"))
    filter_graph_to_session_delta(graph, {"nodes": []})

    assert [(node.file, node.kind, node.symbol_kind) for node in graph.nodes] == [
        ("src/util.ts", "changed", "file")
    ]
    assert graph.edges == []


def test_session_delta_lifts_symbol_edges_between_changed_files(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    src = repo / "src"
    src.mkdir()
    (src / "util.ts").write_text(
        "export function helper() {\n"
        "  return 'old';\n"
        "}\n",
        encoding="utf-8",
    )
    (src / "app.ts").write_text(
        "import { helper } from './util';\n"
        "\n"
        "export function render() {\n"
        "  return 'old';\n"
        "}\n",
        encoding="utf-8",
    )
    _run(["git", "add", "src/app.ts", "src/util.ts"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    (src / "util.ts").write_text(
        "export function helper() {\n"
        "  return 'new';\n"
        "}\n",
        encoding="utf-8",
    )
    (src / "app.ts").write_text(
        "import { helper } from './util';\n"
        "\n"
        "export function render() {\n"
        "  return helper();\n"
        "}\n",
        encoding="utf-8",
    )

    graph = build_graph(collect_diff(str(repo), source="working"))
    assert any(edge.kind == "calls" for edge in graph.edges)

    filter_graph_to_session_delta(graph, {"nodes": []})

    assert {(node.file, node.symbol_kind) for node in graph.nodes} == {
        ("src/app.ts", "file"),
        ("src/util.ts", "file"),
    }
    assert any(
        edge.kind == "calls"
        and graph_node_file(graph, edge.source) == "src/app.ts"
        and graph_node_file(graph, edge.target) == "src/util.ts"
        for edge in graph.edges
    )


def test_session_delta_records_reverted_file_that_disappears_from_current_diff(tmp_path: Path):
    repo = tmp_path / "repo"
    _init_repo(repo)
    file_py = repo / "settings.py"
    file_py.write_text("alpha = 1\n", encoding="utf-8")
    _run(["git", "add", "settings.py"], repo)
    _run(["git", "commit", "-q", "-m", "initial"], repo)

    file_py.write_text("alpha = 2\n", encoding="utf-8")
    previous = serialized_graph_snapshot(build_graph(collect_diff(str(repo), source="working")))

    file_py.write_text("alpha = 1\n", encoding="utf-8")
    graph = build_graph(collect_diff(str(repo), source="working"))
    filter_graph_to_session_delta(graph, previous)

    assert [(node.file, node.summary) for node in graph.nodes] == [
        ("settings.py", "기존 세션 변경을 되돌림")
    ]
    assert "- alpha = 2" in graph.nodes[0].snippet
    assert "+ alpha = 1" in graph.nodes[0].snippet
