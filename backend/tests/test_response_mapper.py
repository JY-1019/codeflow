"""Tests for response_mapper: maps an LLM response onto a change graph."""
from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.changes.git_diff import collect_diff
from app.services.changes.graph_builder import ChangeEdge, ChangeGraph, ChangeNode, build_graph
from app.services.changes.response_mapper import attach_response, _propagate_edge_docs, _split_paragraphs


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True)


def test_split_paragraphs_keeps_code_blocks():
    text = (
        "첫 단락입니다.\n"
        "\n"
        "두 번째 단락.\n"
        "\n"
        "```python\n"
        "def x():\n"
        "    pass\n"
        "```\n"
        "\n"
        "마지막 단락."
    )
    parts = _split_paragraphs(text)
    assert [p.is_code_block for p in parts] == [False, False, True, False]
    assert "def x()" in parts[2].text


def test_edge_fallback_summaries_preserve_direction():
    nodes = [
        ChangeNode(id="source", kind="changed", label="old", file="old.py"),
        ChangeNode(id="target", kind="changed", label="new", file="new.py"),
    ]
    expected = {
        "referenced_by": "`old` uses `new`.",
        "renamed_from": "`old` was renamed to `new`.",
    }

    for kind, summary in expected.items():
        graph = ChangeGraph(
            project_root="/tmp/repo",
            source="working",
            base_ref=None,
            head_ref=None,
            nodes=nodes,
            edges=[ChangeEdge(id=kind, source="source", target="target", kind=kind, label=kind)],
        )
        _propagate_edge_docs(graph)
        assert graph.edges[0].summary == summary


def test_attach_response_links_paragraphs_to_matching_nodes(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)

    (repo / "lib.py").write_text("def hello():\n    return 'hi'\n", encoding="utf-8")
    _git(["add", "lib.py"], repo)
    _git(["commit", "-q", "-m", "init"], repo)

    (repo / "lib.py").write_text(
        "def hello():\n"
        "    return 'hi, world'\n"
        "\n"
        "def goodbye():\n"
        "    return hello()\n",
        encoding="utf-8",
    )

    diff = collect_diff(str(repo), source="working")
    graph = build_graph(diff)

    response = (
        "이번 수정은 `lib.py`의 `hello` 함수에 world를 붙이는 것입니다.\n"
        "\n"
        "또한 `goodbye` 함수를 새로 추가해서 `hello` 를 호출합니다.\n"
        "\n"
        "테스트는 별도 PR에서 다룰 예정입니다."
    )

    attach_response(graph, response)

    hello_node = next(n for n in graph.nodes if n.label == "hello")
    goodbye_node = next(n for n in graph.nodes if n.label == "goodbye")

    assert "world" in hello_node.body or "hello" in hello_node.body
    assert "goodbye" in goodbye_node.body or "추가" in goodbye_node.body
    # unmatched paragraph should fall into narrative
    assert "테스트" in graph.narrative

    # edge summaries get a default human-readable string
    contains_edge = next(e for e in graph.edges if e.kind == "contains")
    assert contains_edge.summary


def test_attach_response_with_empty_text_is_safe(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init", "-q", "-b", "main"], repo)
    _git(["config", "user.email", "t@t"], repo)
    _git(["config", "user.name", "t"], repo)
    (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(["add", "a.py"], repo)
    _git(["commit", "-q", "-m", "init"], repo)
    (repo / "a.py").write_text("x = 2\n", encoding="utf-8")

    graph = build_graph(collect_diff(str(repo), source="working"))
    before_nodes = len(graph.nodes)
    attach_response(graph, "")
    assert len(graph.nodes) == before_nodes
    assert graph.narrative == ""
