# Codeflow Light

**Codex / Claude Code 대화를 Markdown 명령 -> 구현 -> 리뷰 -> 리뷰 반영 -> 검증 흐름으로 보여주는 로컬 데스크탑 시각화 도구.**

Codeflow Light는 백엔드에서 LLM API를 호출하지 않습니다. AI가 이미 만든 사용자 prompt, 최종 응답, 현재 git diff를 받아 한 대화 세션 안의 요청들을 시간순으로 저장합니다. `markdown-branch-push`와 `markdown-branch-commit` capture는 세션/요청 단위로 묶이고, 각 요청 안에서 처리한 Markdown 명령과 구현, 리뷰, 리뷰 반영, 검증, 커밋, push/merge 단계를 flowchart로 보여줍니다. 구현 요약, 리뷰/검증 요약, 기술 고려사항은 로컬에서 계산합니다.

파일은 그래프의 주 노드가 아니라 오른쪽 상세 패널의 확인 정보입니다. 사용자는 각 요청을 클릭해 받은 Markdown 원문, 리뷰 루프 단계별 작업, 파일별 삭제/추가 라인을 확인하고, 그래프에서는 Markdown 명령이 어떤 루프로 처리됐는지를 먼저 봅니다.

## 동작 흐름

```
Codex / Claude prompt + final response ─┐
                                        ├──► /api/sessions/capture
git diff (working / staged / range / branch) ─┘
                                                ▼
                          request group + Markdown workflow + file diff facts
                                                ▼
                        React Flow Markdown review flow + detail panel
```

각 capture step은 다음 정보를 갖습니다.

- `phase`: `implementation`, `review`, `review_fix`, `verification`, `planning`
- `workflow_runs`: Markdown Branch Push/Commit이 처리한 Markdown 명령과 단계 목록
- `implementation`: 구현된 내용 요약
- `review`: 리뷰 finding, 검증, 후속 수정 요약
- `technical_considerations`: 세션 지속성, diff 경계, API 계약, UI 흐름, 검증 등
- `graph`: 이번 step에서 직접 바뀐 파일과 raw 삭제/추가 라인

## 구조

```
codeflow-light/
├── backend/                              # FastAPI, 외부 LLM 호출 없음
│   ├── main.py
│   └── app/
│       ├── routers/changes.py            # changes/session capture API
│       └── services/
│           ├── changes/                  # git diff 수집과 파일 그래프 생성
│           └── sessions/                 # session store + summary enrichment
├── frontend/                             # Electron + Vite + React + @xyflow/react
│   └── src/
│       ├── pages/ChangePage.tsx          # 세션 흐름 / 최종 diff 화면
│       ├── components/SessionFlow.tsx    # Markdown 명령 + 리뷰 루프 flowchart
│       ├── components/DocPanel.tsx       # Markdown 원문 + loop 요약 + 파일별 +/- 라인 패널
│       └── types/changes.ts
└── skill/SKILL.md                        # Codex / Claude Code capture wrapper
```

## 빠른 시작

### 데스크탑 앱

```bash
cd frontend
npm install
npm run desktop
```

Electron 앱이 FastAPI 백엔드를 함께 띄웁니다. 백엔드는 `127.0.0.1:8019`만 사용하며 LLM 키가 필요 없습니다.

패키징:

```bash
cd frontend
npm run dist
```

### 개발 모드

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -e .
python main.py
```

```bash
cd frontend
npm install
npm run dev
```

## 사용 모드

**Session Flow**가 기본 화면입니다. Codex/Claude skill이 보낸 capture를 세션/요청 단위로 묶고, Markdown Branch Push/Commit 요청은 요청 노드 아래에 Markdown 명령 노드와 구현/리뷰/리뷰 반영/검증 루프 노드로 배치합니다. 왼쪽 패널은 전체 Markdown 명령 수와 loop 단계 수를 압축해서 보여주고, 오른쪽 패널은 선택한 요청의 받은 Markdown 원문, loop 단계별 상태, 파일별 삭제/추가 라인을 보여줍니다.

## API

### `POST /api/sessions/capture`

```json
{
  "project_root": "/path/to/repo",
  "source": "branch",
  "user_prompt": "구현 후 리뷰 흐름을 시각화해줘",
  "assistant_response": "구현 요약...",
  "session_id": "optional-stable-session-id"
}
```

응답은 `{ session_id, project_root, branch, groups, latest_group_id, summary }`입니다. 각 group에는 `phase`, `phase_label`, `summary`, `graph`가 포함됩니다.

### `POST /api/changes`

저수준 diff 분석용 API입니다. `source`는 `working`, `staged`, `range`, `branch`를 지원합니다.

## Codex / Claude Skill로 호출

```bash
mkdir -p ~/.codex/skills ~/.claude/skills
ln -sfn "$PWD/skill" ~/.codex/skills/codeflow-light
ln -sfn "$PWD/skill" ~/.claude/skills/codeflow-light
```

이후 Codex/Claude Code에서 "방금 흐름 보여줘" 또는 `/codeflow-light`로 호출하면 skill이 Electron 앱을 자동으로 열고 `/api/sessions/capture`로 현재 step을 저장합니다.

## 테스트

```bash
cd backend
PYTHONPATH=. venv/bin/python -m pytest tests/ -v
```

```bash
cd frontend
npm run typecheck
```
