---
name: codeflow-light
description: |
  Use this skill after a Codex or Claude Code turn that changes code, or whenever
  the user asks to show the current change flow, session timeline, branch review,
  변경 그래프, 수정 시각화, or /codeflow-light. It launches/focuses the local
  Codeflow Light desktop app, captures the user's latest prompt and assistant
  response as one implementation/review step, and sends the current git diff to
  the local backend. No LLM API is called by Codeflow Light.
---

# Codeflow Light

Codeflow Light is a local desktop app for visualizing one coding conversation as
a Markdown command and implementation/review flow. Each Codex/Claude
conversation gets its own desktop window and session history. Each captured turn
becomes one chronological request group named by capture time. Markdown Branch
Push/Commit captures are expanded inside that request group into command,
implementation, review, review-fix, verification, commit, and push/merge nodes.
Files are not the primary graph nodes; they are shown in the right detail panel
as raw deleted/added lines for the selected request.
The step stores:

- `user_prompt`: the user's latest request, shown in the right doc panel when
  the group is clicked.
- `assistant_response`: the final response you are about to send.
- `workflow_runs`: deterministic Markdown Branch Push/Commit command and review
  loop steps inferred from the captured prompt/response.
- file diff facts: only the files directly changed by this specific response.
- deterministic summaries: phase (`implementation`, `review`, `review_fix`,
  `verification`, or `planning`), implementation summary, review summary, and
  technical considerations inferred from the prompt/response/diff facts.

The app has one primary mode:

- **Session Flow**: request groups laid out left-to-right. Markdown Branch
  Push/Commit requests expand into Markdown command -> implementation -> review
  -> review-fix -> verification -> commit -> optional push/merge flow nodes,
  with the received Markdown shown in the right detail panel.

## Capture Workflow

After implementing the user's request and composing the final answer, run the
capture script before sending that final answer.

```bash
SCRIPT="$HOME/.codex/skills/codeflow-light/scripts/codeflow_light_capture.py"
[ -f "$SCRIPT" ] || SCRIPT="$HOME/.claude/skills/codeflow-light/scripts/codeflow_light_capture.py"
python3 "$SCRIPT" --project-root "$PWD" <<'JSON'
{
  "user_prompt": "<copy the user's latest request>",
  "assistant_response": "<copy the final answer you are about to send>",
  "source": "branch"
}
JSON
```

The script will:

1. Install missing frontend dependencies if needed.
2. Build the renderer if the build is missing or stale.
3. Launch/focus the Electron desktop app.
4. Wait for the local FastAPI backend.
5. POST to `/api/sessions/capture`.

Use `CODEFLOW_LIGHT_SESSION_ID` when the caller provides a stable conversation
or task id. In Codex Desktop, the capture script automatically falls back to
`CODEX_THREAD_ID`, so parallel conversations open separate Codeflow windows and
each window shows only that conversation's groups. If no conversation id is
available, the app falls back to repository + branch grouping.

## Summary Quality

The backend does deterministic local summary only. To improve the session flow:

- Mention changed files in backticks, e.g. `frontend/src/pages/ChangePage.tsx`.
- Name whether the step was implementation, review, review-fix, or validation.
- Describe behavior and intent, not syntax trivia.
- Call out technical considerations such as state persistence, API contracts,
  diff boundaries, review gates, validation, and UI flow.
- Keep review findings and review-fix notes in distinct paragraphs when possible.

## Constraints

- Do not call an external LLM API for Codeflow Light docs.
- Do not invent implementation details for `assistant_response`; send only the
  answer you are about to give the user.
- Do not use Codeflow Light to generate line-by-line code comments. The app
  summarizes session steps and technical decisions instead.
- If capture fails, still answer the user and briefly mention the local capture
  error.
