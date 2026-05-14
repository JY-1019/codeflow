"""Smoke tests for the changes pipeline without needing an LLM key."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from app.services.changes.git_diff import collect_diff
from app.services.changes.graph_builder import build_graph
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
    assert any(f.path == "lib.py" for f in diff.files)

    graph = build_graph(diff)
    assert graph.nodes, "expected at least one node"
    labels = {n.label for n in graph.nodes}
    assert "lib.py" in labels
    # symbol-level node for the new function should be present
    assert "goodbye" in labels or "hello" in labels

    # contains edge from file to a symbol
    assert any(e.kind == "contains" for e in graph.edges)
