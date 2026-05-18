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
    assert "1) [수정된 파일]" in body
    assert "백엔드 기본 문서가 diff 라인을 분석해 구현 의도를 담은 fallback 설명을 만들도록 합니다." in body
    assert "`_summarize_code_intent`: 추가/삭제 코드에서 await, React setter, import 같은 신호를 찾아 파일 단위 요약으로 바꿉니다." in body
    assert "라인 수, 추상 분류, 임의 코드 예시를 앞세우던 설명 문구를 제거했습니다." in body
    assert "라인 변화: +2/-1" not in body
    assert "추가된 코드 예" not in body
    assert "```" not in body
    assert "@@ -1,2 +1,8 @@" not in body
