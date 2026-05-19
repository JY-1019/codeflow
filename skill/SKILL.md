---
name: codeflow-light
description: |
  Use this skill during a Codex or Claude Code turn that changes code, or
  whenever the user asks to show the current change flow, session timeline,
  branch review, 변경 그래프, 수정 시각화, or /codeflow-light. It launches/focuses
  the local Codeflow Light desktop app and records implementation/review-loop
  events into the local backend. No LLM API is called by Codeflow Light.
---

# Codeflow Light

Codeflow Light is a local desktop app for visualizing one coding conversation as
a Markdown command and implementation/review flow. Each Codex/Claude
conversation gets its own desktop window and session history. Markdown Branch
Push/Commit workflows should be recorded as live events: Markdown command,
implementation, review, review-fix, verification, commit, and push/merge each
become concrete nodes as soon as that phase completes. Files are not the primary
graph nodes; they are shown in the right detail panel as raw deleted/added lines
for implementation and review-fix nodes.
The session stores:

- `user_prompt`: the user's latest request, shown in the right doc panel when
  the group is clicked.
- `workflow_runs`: explicit Markdown Branch Push/Commit command and review loop
  steps captured while the work runs. Final-response inference is only fallback
  behavior for older captures.
- file diff facts: only the files directly changed by this specific response.
- deterministic summaries: phase (`implementation`, `review`, `review_fix`,
  `verification`, or `planning`), implementation summary, review summary, and
  technical considerations inferred from the prompt/response/diff facts.

The app has one primary mode:

- **Session Flow**: request groups laid out left-to-right. Markdown Branch
  Push/Commit requests expand into Markdown command -> implementation -> review
  -> review-fix -> verification -> commit -> optional push/merge flow nodes.
  Selecting implementation or review-fix nodes shows that phase's captured diff.

## Capture Workflow

When this skill is used together with Markdown Branch Push/Commit, do not wait
for the final response to describe the whole loop. Pick one stable
`workflow_id` for the user's command and one stable `run_id` per Markdown file.
After each phase completes, run the capture script with `--event-kind`:

```bash
SCRIPT="$HOME/.codex/skills/codeflow-light/scripts/codeflow_light_capture.py"
[ -f "$SCRIPT" ] || SCRIPT="$HOME/.claude/skills/codeflow-light/scripts/codeflow_light_capture.py"
WORKFLOW_ID="markdown-review-$(date +%Y%m%d%H%M%S)"

python3 "$SCRIPT" --project-root "$PWD" --event-kind markdown <<JSON
{
  "user_prompt": "<copy the user's latest request>",
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "<stable id for this markdown file>",
  "skill": "markdown-branch-commit",
  "skill_label": "Markdown Branch Commit",
  "command_label": "<markdown title or file name>",
  "markdown_path": "<path/to/request.md>",
  "markdown_content": "<full markdown contents>",
  "step_summary": "Markdown 요청을 구현 단위로 읽었습니다.",
  "step_detail": "<important interpretation/assumptions>",
  "source": "branch"
}
JSON
```

Use the same `workflow_id` and `run_id` for later events in that Markdown file:

```bash
python3 "$SCRIPT" --project-root "$PWD" --event-kind implementation <<JSON
{
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "<stable id for this markdown file>",
  "step_summary": "<what was implemented>",
  "step_detail": "<implementation details>",
  "source": "branch"
}
JSON
```

Record review as its own node, even when there are no findings:

```bash
python3 "$SCRIPT" --project-root "$PWD" --event-kind review <<JSON
{
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "<stable id for this markdown file>",
  "step_summary": "<review result summary>",
  "step_detail": "<findings or no-actionable-finding note>",
  "source": "branch"
}
JSON
```

If review findings are fixed, record a separate `review_fix` event after the
fix is implemented so the node has its own diff:

```bash
python3 "$SCRIPT" --project-root "$PWD" --event-kind review_fix <<JSON
{
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "<stable id for this markdown file>",
  "step_summary": "<how review was addressed>",
  "step_detail": "<specific fixes>",
  "source": "branch"
}
JSON
```

Then capture `verification`, `commit`, and for push workflows `push` and
`merge` events as each phase succeeds or is skipped. Use `step_status:
"skipped"` when the phase intentionally did not run, and `step_status:
"blocked"` when the loop stops on a blocker.

The script will:

1. Launch/focus the Electron desktop app through the bundled
   `bin/codeflow` executable.
2. The executable installs missing frontend dependencies if needed and builds
   the renderer if the build is missing or stale.
3. Start or focus the app window for the current conversation/session.
4. Wait for the local FastAPI backend.
5. POST event payloads to `/api/sessions/event`. Legacy final-turn payloads
   without `--event-kind` still POST to `/api/sessions/capture`.

The capture script looks for `CODEFLOW_LIGHT_EXECUTABLE` first, then the
bundled `bin/codeflow` executable. Use this when testing the desktop app
directly:

```bash
$HOME/.codex/skills/codeflow-light/bin/codeflow --project-root "$PWD"
```

Use `CODEFLOW_LIGHT_SESSION_ID` when the caller provides a stable conversation
or task id. In Codex Desktop, the capture script automatically falls back to
`CODEX_THREAD_ID`, so parallel conversations open separate Codeflow windows and
each window shows only that conversation's groups. If no conversation id is
available, the app falls back to repository + branch grouping.

## Summary Quality

The backend does deterministic local summary only. To improve event nodes:

- Mention changed files in backticks, e.g. `frontend/src/pages/ChangePage.tsx`.
- Describe behavior and intent, not syntax trivia.
- Call out technical considerations such as state persistence, API contracts,
  diff boundaries, review gates, validation, and UI flow.
- Keep review findings and review-fix notes in distinct paragraphs when possible.

## Constraints

- Do not call an external LLM API for Codeflow Light docs.
- Do not invent implementation or review details. Event summaries must describe
  the phase that just actually completed.
- Do not use Codeflow Light to generate line-by-line code comments. The app
  summarizes session steps and technical decisions instead.
- If event capture fails, still continue the implementation loop and briefly
  mention the local capture error in the final answer.
