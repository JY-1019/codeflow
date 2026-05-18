"""Fallback doc generator that runs whether or not an assistant response is provided.

Goal: when the user opens the UI without pasting any LLM response, each node/edge
should still carry a useful, non-empty summary + body built mechanically from
the diff structure itself.

The output is intentionally short and factual ("수정된 함수",
not "this beautifully refactored function ..."). When an LLM response is later
attached via response_mapper.attach_response, those LLM paragraphs are *appended*
on top of these defaults, not replacing them.
"""
from __future__ import annotations

import re

from .graph_builder import ChangeEdge, ChangeGraph, ChangeNode


_STATUS_LABEL_KO: dict[str, str] = {
    "added": "추가됨",
    "modified": "수정됨",
    "deleted": "삭제됨",
    "renamed": "이름 변경",
    "unchanged": "변경 없음",
}

_KIND_LABEL_KO: dict[str, str] = {
    "changed": "직접 변경",
    "affected": "영향 받음",
    "context": "참조 컨텍스트",
    "file": "파일",
}

_SYMBOL_LABEL_KO: dict[str, str] = {
    "file": "파일",
    "function": "함수",
    "method": "메서드",
    "class": "클래스",
    "module": "모듈",
}

_EDGE_KIND_KO: dict[str, str] = {
    "contains": "포함",
    "calls": "참조/호출",
    "imports": "import",
    "referenced_by": "사용처",
    "modifies": "수정",
    "renamed_from": "이름 변경",
}


def fill_default_docs(graph: ChangeGraph) -> None:
    """Populate node.summary/body and edge.summary/body using only diff facts."""
    for node in graph.nodes:
        _fill_node_default(node)
    for edge in graph.edges:
        _fill_edge_default(edge, graph)


def _fill_node_default(node: ChangeNode) -> None:
    status_ko = _STATUS_LABEL_KO.get(node.status, node.status)
    symbol_ko = _SYMBOL_LABEL_KO.get(node.symbol_kind, node.symbol_kind or "심볼")
    kind_ko = _KIND_LABEL_KO.get(node.kind, node.kind)

    if not node.summary:
        if node.kind == "affected":
            node.summary = f"변경된 심볼을 참조하는 외부 {symbol_ko}."
        elif node.status == "added":
            node.summary = f"새로 추가된 {symbol_ko}"
        elif node.status == "deleted":
            node.summary = f"삭제된 {symbol_ko}"
        elif node.status == "renamed":
            node.summary = f"이름이 변경된 {symbol_ko}"
        elif node.status == "modified":
            node.summary = f"수정된 {symbol_ko}"
        else:
            node.summary = f"{kind_ko} · {symbol_ko}"

    if node.body:
        return

    lines: list[str] = [f"1) [{node.summary}]"]

    if node.snippet:
        lines.extend(_plain_change_lines(node.file, node.snippet))
    else:
        lines.extend(_fallback_change_lines(kind_ko, status_ko, symbol_ko))

    if node.kind == "affected":
        lines.append("")
        lines.append("직접 수정된 코드는 아니고, 변경 파일과 연결된 사용처입니다.")

    node.body = "\n".join(lines).strip()


def _plain_change_lines(file_path: str, snippet: str) -> list[str]:
    hunks = _parse_snippet_hunks(snippet)
    if not hunks:
        return [
            "diff 스니펫에서 파일 단위 구현 요약을 만들 단서를 찾지 못했습니다.",
            "세션 요약에는 변경 파일과 단계 정보만 표시됩니다.",
        ]

    all_removed = _flatten_hunk_lines(hunks, "removed")
    all_added = _flatten_hunk_lines(hunks, "added")
    lines = _implementation_lines_for_file(file_path, all_added, all_removed)
    if lines:
        return lines[:5]

    intent = _summarize_code_intent(all_added, all_removed)
    if intent:
        return [
            "구현 내용을 대표하는 변경 신호를 파일 단위로 요약합니다.",
            f"감지된 구현 신호: {intent}",
        ]

    return ["설명 가능한 구현 단서를 찾지 못했습니다. 세션 흐름에서 변경 파일 범위를 확인하세요."]


def _fallback_change_lines(kind_ko: str, status_ko: str, symbol_ko: str) -> list[str]:
    return [
        f"{kind_ko} 대상인 {symbol_ko}의 상태가 {status_ko}로 표시됩니다.",
        "코드 스니펫이 있으면 파일 단위 구현 요약에 반영됩니다.",
    ]


def _parse_snippet_hunks(snippet: str) -> list[dict[str, list[str] | str]]:
    hunks: list[dict[str, list[str] | str]] = []
    current: dict[str, list[str] | str] | None = None

    for line in snippet.splitlines():
        if line.startswith("@@"):
            current = {"header": line.strip(), "added": [], "removed": []}
            hunks.append(current)
            continue
        if line.startswith("+ "):
            if current is None:
                current = {"header": "", "added": [], "removed": []}
                hunks.append(current)
            added = current["added"]
            if isinstance(added, list):
                added.append(line[2:])
        elif line.startswith("- "):
            if current is None:
                current = {"header": "", "added": [], "removed": []}
                hunks.append(current)
            removed = current["removed"]
            if isinstance(removed, list):
                removed.append(line[2:])
    return hunks


def _flatten_hunk_lines(hunks: list[dict[str, list[str] | str]], key: str) -> list[str]:
    flattened: list[str] = []
    for hunk in hunks:
        value = hunk[key]
        if isinstance(value, list):
            flattened.extend(value)
    return flattened


def _summarize_code_intent(added: list[str], removed: list[str]) -> str:
    joined = "\n".join(line.strip() for line in [*added, *removed] if line.strip())
    signals: list[str] = []

    def add_signal(label: str) -> None:
        if label not in signals:
            signals.append(label)

    if re.search(r"\bawait\b|\bfetch[A-Za-z0-9_]*\s*\(", joined):
        add_signal("비동기 데이터 로드")
    if re.search(r"\bset[A-Z][A-Za-z0-9_]*\s*\(", joined):
        add_signal("React 상태 갱신")
    if re.search(r"\bif\s*\(|\?\s*[^:]+:", joined):
        add_signal("조건 처리")
    if re.search(r"^\s*(import|export)\b", joined, re.MULTILINE):
        add_signal("모듈 연결")
    if re.search(r"\b(useEffect|useMemo|useCallback|useState)\s*\(", joined):
        add_signal("React 훅 흐름")
    if re.search(r"<[A-Za-z][A-Za-z0-9.:-]*\b|className=", joined):
        add_signal("화면 표시 조정")
    if re.search(r"\b(type|interface)\s+[A-Za-z_$][\w$]*", joined):
        add_signal("타입 정의")
    if re.search(r"\b(return|throw)\b", joined):
        add_signal("반환/예외 흐름")
    if re.search(r"\b(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=|^\s*[A-Za-z_$][\w$.]*\s*=", joined, re.MULTILINE):
        add_signal("값 계산/할당")
    if re.search(r"\b[A-Za-z_$][\w$.]*\s*\(", joined):
        add_signal("함수 호출")

    return ", ".join(signals[:3])


_KNOWN_IMPLEMENTATIONS: dict[str, str] = {
    "enrich_session_response": "저장된 대화 group에 구현/리뷰 단계와 세션 요약을 붙입니다.",
    "enrich_group": "하나의 capture group에서 phase, 구현 요약, 리뷰 요약, 기술 고려사항을 계산합니다.",
    "build_session_summary": "여러 group에서 최종 구현 범위와 리뷰 흐름을 합산합니다.",
    "technical_considerations": "prompt, 응답, 변경 파일명을 바탕으로 기술 고려사항 카테고리를 추출합니다.",
    "implementation_summary": "라인별 설명 대신 파일 단위 구현 요약을 만듭니다.",
    "review_summary": "리뷰와 검증에 해당하는 문장을 세션 단계 요약으로 정리합니다.",
    "extractDeclarations": "diff에 추가된 함수, 클래스, 타입 선언을 뽑아 노드 요약의 근거로 씁니다.",
    "codexThreadName": "Codex session id로 session_index.jsonl을 역순 검색해 채팅 대화 제목을 찾습니다.",
    "codexHome": "CODEX_HOME 값과 ~ 경로를 안전하게 해석해 Codex 로컬 데이터를 찾습니다.",
    "formatTitleLabel": "창 제목과 헤더 배지에 넣기 좋도록 긴 대화 제목을 한 줄로 줄입니다.",
    "_flatten_hunk_lines": "diff hunk에 흩어진 추가/삭제 라인을 하나의 목록으로 모아 분석 입력으로 만듭니다.",
    "_summarize_code_intent": "추가/삭제 코드에서 await, React setter, import 같은 신호를 찾아 파일 단위 요약으로 바꿉니다.",
}


def _implementation_lines_for_file(file_path: str, added: list[str], removed: list[str]) -> list[str]:
    joined = "\n".join([*added, *removed])
    lines: list[str] = []

    if re.search(r"codexThreadName|CODEFLOW_LIGHT_SESSION_TITLE|sessionTitle", joined):
        lines.append("Codex 세션 id로 채팅 제목을 찾아 Electron 창 제목과 renderer query에 전달합니다.")
    elif re.search(r"WINDOW_SESSION_TITLE|session_title", joined):
        lines.append("Electron이 넘긴 채팅 제목을 화면 헤더 배지에 표시하고 hash는 fallback으로만 씁니다.")
    elif re.search(r"enrich_session_response|build_session_summary|technical_considerations", joined):
        lines.append("세션 group에 구현/리뷰 단계와 기술 고려사항 요약을 붙입니다.")
    elif re.search(r"buildImplementationSummary|selectCoreReviewLines|describeCoreLine", joined):
        lines.append("라인별 코드 설명을 제거하고 파일/단계 중심 요약으로 전환합니다.")
    elif re.search(r"_summarize_code_intent|_flatten_hunk_lines", joined):
        lines.append("백엔드 기본 문서가 diff 라인을 분석해 구현 의도를 담은 fallback 설명을 만들도록 합니다.")
    elif "tests/" in file_path or re.search(r"assert .*핵심|assert .*구현|test_", joined):
        lines.append("새 설명 생성 방식이 실제 구현 요약을 내는지 테스트로 고정합니다.")

    for name in _extract_declarations(added):
        description = _KNOWN_IMPLEMENTATIONS.get(name)
        if description:
            lines.append(f"`{name}`: {description}")

    if any(re.search(r"라인 변화|핵심 흐름|추가된 코드 예", line) for line in removed):
        lines.append("라인 수, 추상 분류, 임의 코드 예시를 앞세우던 설명 문구를 제거했습니다.")

    return _unique(lines)


def _extract_declarations(lines: list[str]) -> list[str]:
    declarations: list[str] = []
    for raw in lines:
        line = raw.strip()
        match = (
            re.match(r"(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", line)
            or re.match(r"def\s+([A-Za-z_][\w]*)\s*\(", line)
            or re.match(r"(?:export\s+)?class\s+([A-Za-z_$][\w$]*)", line)
            or re.match(r"(?:export\s+)?(?:type|interface)\s+([A-Za-z_$][\w$]*)", line)
            or re.match(r"(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", line)
        )
        if match:
            declarations.append(match.group(1))
    return _unique(declarations)


def _unique(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for line in lines:
        if line in seen:
            continue
        seen.add(line)
        output.append(line)
    return output

def _fill_edge_default(edge: ChangeEdge, graph: ChangeGraph) -> None:
    nodes_by_id = {n.id: n for n in graph.nodes}
    src = nodes_by_id.get(edge.source)
    tgt = nodes_by_id.get(edge.target)

    kind_ko = _EDGE_KIND_KO.get(edge.kind, edge.kind)
    src_label = src.label if src else edge.source
    tgt_label = tgt.label if tgt else edge.target

    if not edge.summary:
        if edge.kind == "contains":
            edge.summary = f"`{src_label}` 가 `{tgt_label}` 를 포함합니다."
        elif edge.kind == "calls":
            edge.summary = f"`{src_label}` 가 `{tgt_label}` 를 참조합니다."
        elif edge.kind == "imports":
            edge.summary = f"`{src_label}` 가 `{tgt_label}` 를 import합니다."
        elif edge.kind == "referenced_by":
            edge.summary = f"`{src_label}` 에서 `{tgt_label}` 를 사용합니다."
        elif edge.kind == "renamed_from":
            edge.summary = f"`{src_label}` 가 `{tgt_label}` 로 이름이 바뀌었습니다."
        elif edge.kind == "modifies":
            edge.summary = f"`{src_label}` 의 변경이 `{tgt_label}` 에 적용됩니다."
        else:
            edge.summary = f"`{src_label}` → `{tgt_label}` ({kind_ko})"

    if edge.body:
        return

    lines: list[str] = [f"- **관계**: {kind_ko}"]
    if src:
        lines.append(
            f"- **출발**: `{src.label}` "
            f"({_SYMBOL_LABEL_KO.get(src.symbol_kind, src.symbol_kind)}, {src.file})"
        )
    if tgt:
        lines.append(
            f"- **도착**: `{tgt.label}` "
            f"({_SYMBOL_LABEL_KO.get(tgt.symbol_kind, tgt.symbol_kind)}, {tgt.file})"
        )
    if edge.kind == "imports":
        lines.append("")
        lines.append("> 이 엣지는 현재 파일이 다른 프로젝트 파일의 기능을 import해서 사용하는 관계입니다.")
    if src and src.summary:
        lines.append(f"- **출발 요약**: {src.summary}")
    if tgt and tgt.summary:
        lines.append(f"- **도착 요약**: {tgt.summary}")
    edge.body = "\n".join(lines)
