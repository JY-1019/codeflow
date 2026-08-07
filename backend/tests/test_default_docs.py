from __future__ import annotations

from app.services.changes.default_docs import fill_default_docs
from app.services.changes.graph_builder import ChangeGraph, ChangeNode


def test_default_node_docs_describe_implementation_instead_of_line_counts():
    graph = ChangeGraph(
        project_root="/tmp/repo",
        source="working",
        base_ref=None,
        head_ref=None,
        nodes=[
            ChangeNode(
                id="file::app_py",
                kind="changed",
                label="default_docs.py",
                file="backend/app/services/changes/default_docs.py",
                language="python",
                symbol_kind="file",
                status="modified",
                snippet=(
                    "@@ -1,2 +1,8 @@\n"
                    "- lines.append(\"라인 변화: +2/-1\")\n"
                    "- lines.append(\"추가된 코드 예: `value = 2`\")\n"
                    "+ def _summarize_code_intent(added: list[str], removed: list[str]) -> str:\n"
                    "+     if re.search(r\"\\bawait\\b|\\bfetch[A-Za-z0-9_]*\\s*\\(\", joined):\n"
                    "+         add_signal(\"비동기 데이터 로드\")\n"
                    "+     if re.search(r\"\\bset[A-Z][A-Za-z0-9_]*\\s*\\(\", joined):\n"
                    "+         add_signal(\"React 상태 갱신\")\n"
                ),
                added_lines=5,
                removed_lines=2,
            )
        ],
        edges=[],
    )

    fill_default_docs(graph)

    body = graph.nodes[0].body
    assert "1) [Modified file]" in body
    assert "Makes the backend fallback documentation infer implementation intent from diff lines." in body
    assert "`_summarize_code_intent`: Finds signals such as await, React setters, and imports in changed code for a file-level summary." in body
    assert "Removes descriptions centered on line counts, abstract categories, and arbitrary code examples." in body
    assert "라인 변화: +2/-1" not in body
    assert "추가된 코드 예" not in body
    assert "```" not in body
    assert "@@ -1,2 +1,8 @@" not in body
