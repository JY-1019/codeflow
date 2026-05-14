# Codeflow Light

**Codex / Claude Code의 응답 + 실제 git 변경 = 시각화된 변경 설명.**

백엔드는 LLM API를 호출하지 않습니다. AI가 이미 만든 응답 텍스트를 받아 변경된 파일·심볼 노드에 단락 단위로 매핑하고, 그 결과를 React Flow 그래프로 보여줍니다.

원본 [codeflow](../codeflow)에서 제거한 기능:

- 프로젝트 파일 시스템 sync
- RAG / 임베딩 인덱스
- 문서 자동 생성
- FlowForge / 백엔드 LLM 호출
- 채팅 스트림

남은 한 가지 책임: **AI 응답을 변경 그래프로 시각화**.

## 동작 흐름

```
Codex / Claude Code의 응답 텍스트  ─┐
                                   ├──► /api/changes ──► ChangeGraph
git diff (working / staged / range)─┘                    (nodes + edges + node.body)
                                                                ▼
                                            React Flow + 노드/엣지 doc panel
```

응답의 각 단락은:
1. 인라인 코드(``` `foo.py` `` 또는 `` `hello` ``)와 일반 텍스트에서 파일명/심볼명을 찾는다.
2. 매칭된 노드의 `body`로 첨부된다 (점수 상위 3개 노드).
3. 어디에도 매칭 안 된 단락은 그래프의 `narrative`로 모아 화면 좌측에 표시된다.

LLM은 한 번도 호출되지 않습니다 — 매칭은 단순 토큰 매칭(`re`)으로 처리.

## 구조

```
codeflow-light/
├── backend/                              # FastAPI (LLM 호출 없음)
│   ├── main.py
│   └── app/
│       ├── routers/
│       │   ├── health.py
│       │   └── changes.py
│       └── services/changes/
│           ├── git_diff.py               # working/staged/range diff 파싱
│           ├── symbol_extractor.py       # Python/TS/Go/Java 심볼 추출 (정규식)
│           ├── graph_builder.py          # diff + 심볼 → 노드/엣지
│           └── response_mapper.py        # AI 응답 단락 → 노드 body 매핑
├── frontend/                             # Vite + React + @xyflow/react
│   └── src/
│       ├── pages/ChangePage.tsx          # 3분할: 응답 · 그래프 · 노드 doc
│       ├── components/
│       │   ├── NarrativePanel.tsx
│       │   ├── ChangeFlow.tsx
│       │   ├── DocPanel.tsx
│       │   ├── nodes/ChangeNodeView.tsx
│       │   └── edges/ChangeEdgeView.tsx
│       └── api/client.ts
└── skill/SKILL.md                        # Claude Code skill wrapper
```

## 노드/엣지 모델

| node kind | 의미                                                                  |
| --------- | --------------------------------------------------------------------- |
| changed   | AI가 추가/수정한 파일·함수·클래스                                     |
| affected  | 변경된 심볼을 참조하는 다른 파일 (`git grep`로 자동 발견)             |

| edge kind     | 의미                                       |
| ------------- | ------------------------------------------ |
| contains      | 파일이 함수/클래스를 포함                  |
| calls         | 변경 심볼이 다른 변경 심볼을 호출/참조     |
| referenced_by | 외부 파일이 변경 심볼을 사용               |
| renamed_from  | 이름 변경                                  |

각 노드의 `body`는 AI 응답의 관련 단락. 각 엣지의 `summary`는 양 끝 노드 정보로 생성된 기본 문장 (LLM 미사용).

## 빠른 시작

### 1. 백엔드

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -e .
python main.py        # 127.0.0.1:8019, LLM 키 불필요
```

### 2. 프론트엔드

```bash
cd frontend
npm install
npm run dev           # http://localhost:5174
```

### 3. 사용

1. 브라우저에서 `http://localhost:5174`.
2. `project root`에 git 저장소 경로 입력.
3. `AI 응답` 영역에 Codex/Claude Code가 만든 응답을 그대로 붙여넣기.
4. **분석** 클릭 → 변경 그래프 + 매핑된 노드 doc + 미매핑 narrative 표시.
5. 노드/엣지를 클릭하면 우측에 해당 단락 + diff snippet.

## API

### `POST /api/changes`

```json
{
  "project_root": "/path/to/repo",
  "source": "working", // "working" | "staged" | "range"
  "base_ref": null, // range일 때 필수
  "head_ref": null,
  "assistant_response": "이번 수정은 `lib.py`의 `hello` 함수를..."
}
```

응답: `{ nodes, edges, narrative, warnings, ... }` — 자세한 스키마는 `frontend/src/types/changes.ts`의 `ChangeGraphResponse`.

`assistant_response`가 빈 문자열이면 그래프 구조만 반환되고 노드/엣지 body는 빈 채로 남습니다.

## Claude Code Skill로 호출

```bash
mkdir -p ~/.claude/skills/codeflow-light
ln -sf "$PWD/skill/SKILL.md" ~/.claude/skills/codeflow-light/SKILL.md
```

이후 Claude Code에서 "방금 한 변경 보여줘" 또는 `/codeflow-light`로 호출 가능. 자세한 호출 규약은 `skill/SKILL.md` 참고.

## 테스트

```bash
cd backend
PYTHONPATH=. venv/bin/python -m pytest tests/ -v
```

5 tests: 심볼 추출, diff→graph 파이프라인, 단락 분리, 응답↔노드 매핑, 빈 응답 안전성.
