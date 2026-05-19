# Codeflow Light

**Codex / Claude Code 대화를 Markdown 명령 -> 구현 -> 리뷰 -> 리뷰 반영 -> 검증 흐름으로 보여주는 로컬 데스크탑 시각화 도구.**

Codeflow Light는 백엔드에서 LLM API를 호출하지 않습니다. `markdown-branch-push`와 `markdown-branch-commit` workflow가 실행되는 동안 Markdown 명령, 구현, 리뷰, 리뷰 반영, 검증, 커밋, push/merge 이벤트를 로컬 API에 하나씩 기록합니다. 각 이벤트는 세션/요청 단위로 묶이고, Electron 화면은 진행 중인 리뷰 루프를 poll해서 flowchart로 갱신합니다. 구현 요약, 리뷰/검증 요약, 기술 고려사항은 로컬에서 계산합니다.

파일은 그래프의 주 노드가 아니라 오른쪽 상세 패널의 확인 정보입니다. 사용자는 구현 node와 리뷰 반영 node를 클릭해 해당 단계에서 실제로 생긴 diff를 확인하고, 리뷰 node에서는 리뷰 결과 요약만 읽습니다. 그래프에서는 Markdown 명령이 어떤 루프로 처리됐는지를 먼저 봅니다.

## 동작 흐름

```
Markdown command event ─┐
Implementation event ───┤
Review event ───────────┼──► /api/sessions/event
Review-fix event ───────┤
Verify/commit/push ─────┘
                         │
git diff snapshot ───────┘
                         ▼
         request group + explicit workflow nodes + per-step diff facts
                         ▼
        Electron Session Flow + implementation/review detail panel
```

기존 final-response 기반 capture는 `/api/sessions/capture` fallback으로 남아 있지만, Markdown 리뷰 루프의 기본 경로는 `/api/sessions/event`입니다. 각 event step은 다음 정보를 갖습니다.

- `phase`: `implementation`, `review`, `review_fix`, `verification`, `planning`
- `workflow_runs`: Markdown Branch Push/Commit이 처리한 Markdown 명령과 단계 목록
- `implementation`: 구현된 내용 요약
- `review`: 리뷰 finding, 검증, 후속 수정 요약
- `technical_considerations`: 세션 지속성, diff 경계, API 계약, UI 흐름, 검증 등
- `graph`: 해당 step에서 직접 바뀐 파일과 raw 삭제/추가 라인

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
└── skill/
    ├── bin/codeflow                      # Desktop app launcher executable
    └── SKILL.md                          # Codex / Claude Code capture wrapper
```

## 빠른 시작

### 데스크탑 앱

```bash
./skill/bin/codeflow --project-root "$PWD"
```

`codeflow` 실행 파일이 필요한 frontend dependency를 설치하고 renderer build가 없거나 stale하면 다시 build한 뒤 Electron 앱을 띄웁니다. Electron 앱이 FastAPI 백엔드를 함께 띄웁니다. 백엔드는 `127.0.0.1:8019`만 사용하며 LLM 키가 필요 없습니다.

개발 중 직접 npm script를 사용해도 됩니다.

```bash
cd frontend
npm install
npm run desktop
```

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

**Session Flow**가 기본 화면입니다. Codex/Claude skill이 보낸 event를 세션/요청 단위로 묶고, Markdown Branch Push/Commit 요청은 Markdown 명령 노드와 구현/리뷰/리뷰 반영/검증 루프 노드로 배치합니다. 왼쪽 패널은 전체 Markdown 명령 수와 loop 단계 수를 압축해서 보여주고, 오른쪽 패널은 선택한 단계의 요약과 파일별 삭제/추가 라인을 보여줍니다.

## API

### `POST /api/sessions/event`

```json
{
  "project_root": "/path/to/repo",
  "source": "branch",
  "session_id": "optional-stable-session-id",
  "workflow_id": "stable-id-for-this-user-command",
  "run_id": "stable-id-for-one-markdown-file",
  "skill": "markdown-branch-commit",
  "markdown_path": "requests/01-ui.md",
  "step_kind": "implementation",
  "step_summary": "SessionFlow가 구현/리뷰/리뷰 반영 node를 표시하도록 수정했습니다.",
  "step_detail": "구현 단계에서 바뀐 내용을 설명합니다.",
  "step_status": "completed"
}
```

`step_kind`는 `preflight`, `markdown`, `branch`, `implementation`, `review`, `review_fix`, `verification`, `commit`, `push`, `merge`를 지원합니다.

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

응답은 `{ session_id, project_root, branch, groups, latest_group_id, summary }`입니다. 각 group에는 `phase`, `phase_label`, `summary`, `workflow_runs`, `graph`가 포함됩니다.

### `POST /api/changes`

저수준 diff 분석용 API입니다. `source`는 `working`, `staged`, `range`, `branch`를 지원합니다.

## Codex / Claude Skill로 호출

```bash
mkdir -p ~/.codex/skills ~/.claude/skills
ln -sfn "$PWD/skill" ~/.codex/skills/codeflow-light
ln -sfn "$PWD/skill" ~/.claude/skills/codeflow-light
```

이후 Codex/Claude Code에서 Markdown Branch skill과 `codeflow-light`를 함께 호출하면 skill이 Electron 앱을 자동으로 열고 `/api/sessions/event`로 각 단계를 저장합니다. "방금 흐름 보여줘" 또는 `/codeflow-light`처럼 단독 호출한 경우에는 legacy `/api/sessions/capture` fallback으로 현재 diff를 저장할 수 있습니다.

skill의 capture script는 `CODEFLOW_LIGHT_EXECUTABLE`이 있으면 그 경로를 우선 사용하고, 없으면 `~/.codex/skills/codeflow-light/bin/codeflow` 또는 skill에 번들된 실행 파일을 사용합니다.

## 테스트

```bash
cd backend
PYTHONPATH=. venv/bin/python -m pytest tests/ -v
```

```bash
cd frontend
npm run typecheck
```
