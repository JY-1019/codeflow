# Codeflow Light

**Codex / Claude Code 작업을 구현 -> 리뷰 -> 리뷰 반영 -> 검증 흐름으로 보여주는 로컬 데스크탑 시각화 도구.**

Codeflow Light는 두 부분으로 동작합니다.

- **데스크탑 앱**: GitHub Releases에서 받은 DMG/EXE로 설치하는 Electron 앱입니다. 로컬 FastAPI 백엔드를 함께 띄우고 `127.0.0.1:8019`에서 이벤트를 받습니다.
- **Codex / Claude Code 플러그인 또는 Skill**: 작업 중 구현, 리뷰, 리뷰 반영, 검증 이벤트를 데스크탑 앱으로 보내는 얇은 호출 어댑터입니다.

플러그인은 DMG를 자동 설치하지 않습니다. 먼저 데스크탑 앱을 설치한 뒤, Codex 또는 Claude Code에서 `codeflow-light`를 명시 호출하면 그 작업 안에서 이벤트가 기록됩니다. Codeflow Light 자체는 외부 LLM API를 호출하지 않습니다.

## 빠른 시작

### 1. 데스크탑 앱 설치

1. [GitHub Releases](https://github.com/jongyeon1019/Codeflow-light/releases/latest)에서 최신 `Codeflow-Light-<version>-<arch>.dmg`를 내려받습니다.
2. DMG를 열고 `Codeflow Light.app`을 `/Applications`로 옮깁니다.
3. 앱을 한 번 실행합니다. macOS가 차단하면 Finder에서 앱을 control-click한 뒤 `Open`을 선택합니다.

Windows 사용자는 release의 `Codeflow-Light-<version>-x64.exe` portable 실행 파일을 사용합니다. 플러그인이 앱을 찾을 수 있도록 내려받은 EXE 경로를 지정하세요.

```powershell
setx CODEFLOW_LIGHT_APP_EXECUTABLE "C:\path\to\Codeflow-Light-0.1.0-x64.exe"
```

### 2. Codex / Claude Code 연결

이 저장소 루트는 Codex와 Claude Code 플러그인 루트입니다.

- Codex manifest: `.codex-plugin/plugin.json`
- Claude Code manifest: `.claude-plugin/plugin.json`
- Plugin skill wrapper: `skills/codeflow-light/SKILL.md`
- Canonical skill instructions: `skill/SKILL.md`
- Plugin PATH wrappers: `bin/codeflow`, `bin/codeflow-light-capture`

로컬 checkout에서 Claude Code 플러그인을 확인하려면:

```bash
claude plugin validate .
claude --plugin-dir "$PWD" plugin details codeflow-light
```

Claude Code에서 플러그인으로 로드되면 작업 요청에 `codeflow-light`를 명시해 plugin skill을 호출합니다.

기존 Skill 방식으로 직접 연결할 수도 있습니다.

```bash
mkdir -p ~/.codex/skills ~/.claude/skills
ln -sfn "$PWD/skill" ~/.codex/skills/codeflow-light
ln -sfn "$PWD/skill" ~/.claude/skills/codeflow-light
```

Codex 플러그인 manifest를 로컬에서 검증하려면:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py "$PWD"
```

### 3. 작업에서 호출

Codeflow Light는 백그라운드 감시기가 아닙니다. 작업 요청에 `codeflow-light`를 명시해야 그 요청의 구현/리뷰 루틴을 기록합니다.

Codex 안에서 구현하고 Codex `/review`까지 기록하는 예:

```text
codeflow-light로 이번 구현과 리뷰 루틴을 Codeflow Light에 기록해줘.
구현 후 Codex review를 품질 게이트로 실행하고, 지적사항이 있으면 반영 후 재리뷰해줘.
검증까지 기록하고 commit/push는 하지 마.
```

Claude Code에서 구현하고 Claude Code 안의 Codex review plugin이 리뷰하는 예:

```text
codeflow-light로 이번 변경을 구현하고 Codeflow Light에 기록해줘.
구현 단계는 Claude Code, 리뷰 단계는 Codex review plugin이 수행한 것으로 agent를 구분해줘.
리뷰 지적사항이 있으면 반영하고 재리뷰해줘.
검증까지 기록하고 commit/push는 생략해.
```

더 긴 복붙용 예시는 [`prompts/`](prompts/)를 참고하세요.

## 무엇이 기록되나

기본 기록 단위는 `/api/sessions/event` 이벤트입니다.

- `implementation`: 실제 구현 단계와 해당 단계의 diff
- `review`: 리뷰 결과 요약. 지적사항이 없어도 별도 노드로 기록
- `review_fix`: 리뷰 지적사항을 반영한 단계와 해당 단계의 diff
- `verification`: 실행한 focused test, typecheck, build 등
- `commit`, `push`, `merge`: 다른 workflow가 수행한 경우에만 기록. Codeflow Light 단독 사용에서는 생략해도 됩니다.

각 step은 `agent`를 가질 수 있습니다.

- Codex 내부 루틴: `agent: "codex"`
- Claude Code 구현: `agent: "claude-code"`
- Claude Code 안의 Codex review plugin 리뷰: `agent: "codex"`

같은 `workflow_id`와 `run_id`를 공유하면 구현, 리뷰, 리뷰 반영, 검증이 하나의 traceable run으로 묶이고, UI에는 단계별 수행 주체 badge가 표시됩니다.

## 동작 방식

```text
사용자 prompt
  -> Codex / Claude Code plugin 또는 Skill
  -> codeflow-light-capture
  -> 설치된 Codeflow Light.app / EXE 실행 또는 focus
  -> local FastAPI backend
  -> Electron Session Flow
```

capture script는 먼저 plugin PATH의 `codeflow-light-capture`를 찾습니다. 없으면 기존 Skill 설치 경로를 사용합니다.

```bash
SCRIPT="$(command -v codeflow-light-capture || true)"
[ -n "$SCRIPT" ] || SCRIPT="$HOME/.codex/skills/codeflow-light/scripts/codeflow_light_capture.py"
[ -f "$SCRIPT" ] || SCRIPT="$HOME/.claude/skills/codeflow-light/scripts/codeflow_light_capture.py"
```

launcher는 설치된 앱을 우선 사용합니다.

- macOS: `/Applications/Codeflow Light.app/Contents/MacOS/Codeflow Light`
- Windows: `CODEFLOW_LIGHT_APP_EXECUTABLE` 또는 기본 설치 위치

앱이 설치되어 있지 않으면 정상 사용자 경로에서는 capture가 실패합니다. 개발 중 repository-local Electron fallback을 사용하려면 명시적으로 켭니다.

```bash
CODEFLOW_LIGHT_ALLOW_DEV_LAUNCH=1 ./skill/bin/codeflow --project-root "$PWD"
```

## 화면

**Session Flow**가 기본 화면입니다. 요청 group을 왼쪽에서 오른쪽으로 배치하고, Markdown Branch 요청은 Markdown 명령 -> 구현 -> 리뷰 -> 리뷰 반영 -> 검증 -> optional commit/push/merge 노드로 펼칩니다.

파일은 주 그래프 노드가 아니라 오른쪽 상세 패널의 확인 정보입니다. 구현 node와 리뷰 반영 node를 클릭하면 해당 단계에서 실제로 생긴 raw added/deleted line을 볼 수 있고, 리뷰 node에서는 리뷰 결과 요약을 봅니다.

## 개발과 패키징

개발 모드:

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

macOS DMG 빌드:

```bash
cd frontend
npm run dist:mac
```

산출물은 `frontend/release/Codeflow-Light-<version>-<arch>.dmg`입니다. 이 파일은 Git에 커밋하지 말고 GitHub Release asset으로 업로드합니다.

Windows portable EXE 빌드:

```bash
cd frontend
npm run dist:win
```

산출물은 `frontend/release/Codeflow-Light-<version>-x64.exe`입니다.

## API

### `POST /api/sessions/event`

```json
{
  "project_root": "/path/to/repo",
  "source": "branch",
  "session_id": "optional-stable-session-id",
  "workflow_id": "stable-id-for-this-user-command",
  "run_id": "stable-id-for-one-unit",
  "skill": "general",
  "command_label": "문서 정리",
  "step_kind": "implementation",
  "agent": "claude-code",
  "step_summary": "README의 설치 흐름을 정리했습니다.",
  "step_detail": "DMG 설치, 플러그인 연결, 호출 예시를 분리했습니다.",
  "step_status": "completed"
}
```

`step_kind`는 `preflight`, `markdown`, `branch`, `implementation`, `review`, `review_fix`, `verification`, `commit`, `push`, `merge`를 지원합니다.

### `POST /api/sessions/capture`

이전 final-response 기반 fallback입니다. 새 리뷰 루프 기록에는 `/api/sessions/event`를 사용합니다.

### `POST /api/changes`

저수준 diff 분석용 API입니다. `source`는 `working`, `staged`, `range`, `branch`를 지원합니다.

## 저장소 구조

```text
codeflow-light/
├── .codex-plugin/plugin.json             # Codex plugin manifest
├── .claude-plugin/plugin.json            # Claude Code plugin manifest
├── bin/                                  # plugin PATH wrappers
├── backend/                              # FastAPI, 외부 LLM 호출 없음
├── frontend/                             # Electron + Vite + React + @xyflow/react
├── prompts/                              # portable prompt examples
├── skill/                                # canonical Skill instructions + launcher
└── skills/codeflow-light/                # plugin Skill wrapper
```

## 검증

```bash
pytest -q backend/tests
```

```bash
cd frontend
npm run typecheck
npm run build
```

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py "$PWD"
claude plugin validate .
```
