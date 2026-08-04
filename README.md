# Codeflow

**A local desktop visualizer for Codex and Claude Code implementation -> review -> review-fix -> verification loops.**

Codeflow has two parts:

- **Desktop app**: a packaged Electron app. It starts a local FastAPI backend and receives workflow events on `127.0.0.1:8019`.
- **Codex / Claude Code plugin or Skill**: a thin adapter that records implementation, review, review-fix, and verification events while an agent works.

The plugin does not download or install the desktop app for you. Install it first, then explicitly invoke `codeflow` in Codex or Claude Code when you want a task to be recorded. Codeflow itself does not call any external LLM API.

## Quick Start

### 1. Install The Desktop App

1. Until a renamed release is published, build the macOS DMG with `cd frontend && npm ci && npm run dist:mac`.
2. Open `frontend/release/Codeflow-<version>-<arch>.dmg` and drag `Codeflow.app` into `/Applications`.
3. Launch the app once. If macOS blocks it, control-click the app in Finder and choose `Open`.

If a Windows portable EXE is provided as a release asset, set the executable path so the plugin can launch it:

```powershell
setx CODEFLOW_APP_EXECUTABLE "C:\path\to\Codeflow-0.1.0-x64.exe"
```

### 2. Connect Codex Or Claude Code

This repository root is also the plugin root.

- Codex manifest: `.codex-plugin/plugin.json`
- Claude Code manifest: `.claude-plugin/plugin.json`
- Plugin skill wrapper: `skills/codeflow/SKILL.md`
- Canonical skill instructions: `skill/SKILL.md`
- Plugin PATH wrappers: `bin/codeflow`, `bin/codeflow-capture`

To validate the Claude Code plugin from a local checkout:

```bash
claude plugin validate .
claude --plugin-dir "$PWD" plugin details codeflow
```

When the plugin is loaded in Claude Code, mention `codeflow` in the task prompt to invoke the plugin skill.

You can also install the legacy Skill layout directly:

```bash
mkdir -p ~/.codex/skills ~/.claude/skills
ln -sfn "$PWD/skill" ~/.codex/skills/codeflow
ln -sfn "$PWD/skill" ~/.claude/skills/codeflow
```

To validate the Codex plugin manifest locally:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py "$PWD"
```

### 3. Invoke It During Work

Codeflow is not a background watcher. Add `codeflow` to the task prompt when you want the implementation/review loop recorded.

Example: Codex implements and Codex `/review` reviews:

```text
Use codeflow to record this implementation and review loop.
After implementing, run Codex review as the quality gate, fix actionable findings, and review again.
Record verification as well. Do not commit or push.
```

Example: Claude Code implements and the Codex review plugin reviews:

```text
Use codeflow to implement this change and record the workflow.
Mark the implementation phase as Claude Code and the review phase as the Codex review plugin.
Fix review findings, review again, and record verification. Skip commit and push.
```

Longer copy-paste prompts are available in [`prompts/`](prompts/).

## What Gets Recorded

The primary recording unit is a `POST /api/sessions/event` event.

- `implementation`: the implementation step and its diff
- `review`: the review result summary, including no-finding reviews
- `review_fix`: the step that addresses review findings and its diff
- `verification`: focused tests, typechecks, builds, or other checks
- `commit`, `push`, `merge`: optional events recorded only when another workflow performs them

Each step can include an `agent` value.

- Claude Code implementation -> Codex review: `claude-code` -> `codex`
- Codex implementation -> Codex review: `codex` -> `codex`
- Claude Code implementation -> Claude Code review: `claude-code` -> `claude-code`
- Codex implementation -> Claude Code review: `codex` -> `claude-code`

Events with the same `session_id`, `workflow_id`, and `run_id` are grouped into one traceable run. Set `CODEFLOW_SESSION_ID` to the same value on both sides of a cross-tool handoff. The UI shows a small agent badge on every workflow step, including `branch`, `commit`, `push`, and `merge` events.

## How It Works

```text
user prompt
  -> Codex / Claude Code plugin or Skill
  -> codeflow-capture
  -> installed Codeflow.app / EXE launch or focus
  -> local FastAPI backend
  -> Electron Session Flow UI
```

The capture script prefers the plugin PATH wrapper first, then falls back to legacy Skill installation paths:

```bash
SCRIPT="$(command -v codeflow-capture || true)"
[ -n "$SCRIPT" ] || SCRIPT="$HOME/.codex/skills/codeflow/scripts/codeflow_capture.py"
[ -f "$SCRIPT" ] || SCRIPT="$HOME/.claude/skills/codeflow/scripts/codeflow_capture.py"
```

The launcher prefers the installed packaged app:

- macOS: `/Applications/Codeflow.app/Contents/MacOS/Codeflow`
- Windows: the portable EXE path set in `CODEFLOW_APP_EXECUTABLE`

If the installed app is missing, normal user flows fail clearly. Repository-local Electron fallback is only for development:

```bash
CODEFLOW_ALLOW_DEV_LAUNCH=1 ./skill/bin/codeflow --project-root "$PWD"
```

## UI

The main screen is **Session Flow**. It lays out request groups from left to right and expands Markdown Branch workflows into:

```text
Markdown command -> implementation -> review -> review_fix -> verification -> optional commit/push/merge
```

Files are shown in the right-side detail panel, not as primary graph nodes. Click an implementation or review-fix node to inspect raw added/deleted lines. Click a review node to inspect the review summary.

## Development

Backend:

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -e .
python main.py
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Build a macOS DMG:

```bash
cd frontend
npm run dist:mac
```

The DMG is written to `frontend/release/Codeflow-<version>-<arch>.dmg`. Do not commit this file to Git; upload it as a GitHub Release asset.

Build a Windows portable EXE from a Windows environment:

```bash
cd frontend
npm run dist:win
```

The EXE is written to `frontend/release/Codeflow-<version>-x64.exe`.

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
  "command_label": "Documentation cleanup",
  "step_kind": "implementation",
  "agent": "claude-code",
  "step_summary": "Updated README installation flow.",
  "step_detail": "Separated DMG installation, plugin setup, and invocation examples.",
  "step_status": "completed"
}
```

Supported `step_kind` values:

```text
preflight, markdown, branch, implementation, review, review_fix, verification, commit, push, merge
```

### `POST /api/sessions/capture`

Legacy final-response fallback. New review-loop integrations should use `/api/sessions/event`.

### `POST /api/changes`

Low-level diff analysis API. Supported `source` values are `working`, `staged`, `range`, and `branch`.

## Repository Layout

```text
codeflow/
├── .codex-plugin/plugin.json      # Codex plugin manifest
├── .claude-plugin/plugin.json     # Claude Code plugin manifest
├── bin/                           # plugin PATH wrappers
├── backend/                       # FastAPI, no external LLM calls
├── frontend/                      # Electron + Vite + React + @xyflow/react
├── prompts/                       # portable prompt examples
├── skill/                         # canonical Skill instructions + launcher
└── skills/codeflow/         # plugin Skill wrapper
```

## Validation

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
