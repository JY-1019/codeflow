---
name: codeflow-light
description: |
  Use this skill only when the user explicitly invokes Codeflow Light, for
  example with codeflow-light, /codeflow-light, or a direct request to open,
  show, or record Codeflow Light. Do not use it automatically for ordinary code
  changes, reviews, or Markdown Branch workflows unless the user also asks for
  Codeflow Light. It works the same from Claude Code and from Codex, and records
  which tool/agent performed each step, so a "Claude Code implements, then Codex
  review plugin reviews" loop (or an implement/review loop repeated entirely in
  Claude Code) stays traceable. When invoked on its own in a general request, it
  also records ad-hoc work as a general capture even without a fixed Markdown
  Branch format. It launches/focuses the local Codeflow Light desktop app and
  records implementation/review-loop events into the local backend. No LLM API
  is called by Codeflow Light.
---

# Codeflow Light

Codeflow Light is a local desktop app for visualizing one coding conversation as
a Markdown command and implementation/review flow. Each Codex/Claude
conversation gets its own desktop window and session history. Markdown Branch
Push/Commit workflows should be recorded as live events: Markdown command,
implementation, review, review-fix, verification, commit, and push/merge each
become concrete nodes as soon as that phase completes. User-facing event
summaries, review notes, status labels, and skill labels must be written in
Korean. Files are not the primary graph nodes; they are shown in the right
detail panel as raw deleted/added lines for implementation and review-fix nodes.
This skill does not install the desktop app or DMG. It only launches/focuses an
already installed Codeflow Light app and sends local capture events to it. If
commit, push, or merge are not part of the user's requested workflow, skip those
events or record them as skipped; implementation, review, review-fix, and
verification are enough for normal review-loop tracking.
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

Only run the capture workflow after the user explicitly invokes Codeflow Light.
When this skill is explicitly used together with Markdown Branch Push/Commit, do
not wait for the final response to describe the whole loop. Pick one stable
`workflow_id` for the user's command and one stable `run_id` per Markdown file.
After each phase completes, run the capture script with `--event-kind`:

```bash
SCRIPT="$(command -v codeflow-light-capture || true)"
[ -n "$SCRIPT" ] || SCRIPT="$HOME/.codex/skills/codeflow-light/scripts/codeflow_light_capture.py"
[ -f "$SCRIPT" ] || SCRIPT="$HOME/.claude/skills/codeflow-light/scripts/codeflow_light_capture.py"
WORKFLOW_ID="markdown-review-$(date +%Y%m%d%H%M%S)"

python3 "$SCRIPT" --project-root "$PWD" --event-kind markdown <<JSON
{
  "user_prompt": "<copy the user's latest request>",
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "<stable id for this markdown file>",
  "skill": "markdown-branch-commit",
  "skill_label": "Markdown 브랜치 커밋",
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
  "step_summary": "<무엇을 구현했는지 한국어로 요약>",
  "step_detail": "<구현 세부사항을 한국어로 설명>",
  "source": "branch"
}
JSON
```

Record review as its own node, even when there are no findings. Set `agent` to
the tool that actually ran the review — for example `codex` when the Codex
review plugin reviews work that Claude Code implemented:

```bash
python3 "$SCRIPT" --project-root "$PWD" --event-kind review <<JSON
{
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "<stable id for this markdown file>",
  "agent": "codex",
  "step_summary": "<리뷰 결과를 한국어로 요약>",
  "step_detail": "<리뷰 지적사항 또는 조치할 지적사항이 없었다는 내용을 한국어로 설명>",
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
  "step_summary": "<리뷰를 어떻게 반영했는지 한국어로 요약>",
  "step_detail": "<구체적인 수정 내용을 한국어로 설명>",
  "source": "branch"
}
JSON
```

Then capture `verification`. Capture `commit`, and for push workflows `push`
and `merge`, only when the workflow actually performs those phases. Use
`step_status: "skipped"` when a phase is intentionally not run, and
`step_status: "blocked"` when the loop stops on a blocker.

## Cross-tool tracking (Claude Code + Codex)

Each event accepts an `agent` field naming the tool that performed that step.
When omitted, the capture script infers the host tool from the environment
(`claude-code` or `codex`), so a loop run entirely inside one tool is labelled
automatically. Set `agent` explicitly when the implement and review phases use
different tools — for example Claude Code implements (`agent: "claude-code"`)
and the in-Claude Codex review plugin reviews (`agent: "codex"`). Known agent
slugs (`claude-code`, `codex`) get friendly labels; any other slug is shown
as-is. Because `workflow_id`/`run_id` stay stable across the loop, repeating
implement -> review -> review-fix in the same tool, or mixing tools per phase,
both render as one traceable run with per-step actor badges.

## General capture (no fixed workflow)

When the user invokes Codeflow Light on its own in a general request that is not
a Markdown Branch workflow, still record what was done. Use `skill: "general"`
(or `skill: "codeflow-light"`), pick one `workflow_id` for the request and one
`run_id` for the unit of work, set `command_label` to a short Korean title, and
emit `implementation` / `review` / `verification` events as each part of the
work completes:

```bash
WORKFLOW_ID="codeflow-general-$(date +%Y%m%d%H%M%S)"
python3 "$SCRIPT" --project-root "$PWD" --event-kind implementation <<JSON
{
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "ad-hoc",
  "skill": "general",
  "command_label": "<무엇을 했는지 한국어 제목>",
  "step_summary": "<한국어로 작업 요약>",
  "step_detail": "<한국어로 세부 내용>",
  "source": "working"
}
JSON
```

This records ad-hoc work as a normal session run, so the desktop app shows what
was done and which tool did it even without a fixed Markdown Branch format.

Capture is best-effort and must never block the implementation/review loop.
Give each capture attempt a short window, about 20-30 seconds. If the app launch
or backend wait is still pending after that window, stop waiting, continue the
coding workflow, and mention the local capture timeout in the final response.
Do not retry capture in a tight loop. Later phase captures may still be
attempted once each.

When the Markdown or Obsidian requirement includes images, do not embed image
bytes or base64 in the event payload. Preserve the Markdown content as text and
write resolved image paths plus the observed requirement-relevant details in
Korean inside `step_detail`.

The script will:

1. Launch/focus the Electron desktop app through the bundled
   `bin/codeflow` executable.
2. The executable uses the installed packaged app by default:
   `/Applications/Codeflow Light.app/Contents/MacOS/Codeflow Light` on macOS,
   or the path in `CODEFLOW_LIGHT_APP_EXECUTABLE` for a portable/installed
   Windows EXE.
3. Start or focus the app window for the current conversation/session.
4. Wait for the local FastAPI backend.
5. POST event payloads to `/api/sessions/event`. Legacy final-turn payloads
   without `--event-kind` still POST to `/api/sessions/capture`.

Do not use repository-local `npm` or Python launch paths for normal usage. The
installed DMG/EXE is the runtime surface. This skill must not try to download
or install a DMG/EXE on the user's behalf. The repository-local development
fallback is available only when `CODEFLOW_LIGHT_ALLOW_DEV_LAUNCH=1` is
explicitly set for local development.

The capture script looks for `CODEFLOW_LIGHT_EXECUTABLE` first, then the
bundled `bin/codeflow` executable. Use this when testing the desktop app
directly:

```bash
$HOME/.codex/skills/codeflow-light/bin/codeflow --project-root "$PWD"
```

## Packaged App Runtime

The macOS DMG and Windows EXE are the normal runtime targets for this skill. The
packaged app must run the monitoring UI and local backend without requiring the
user to keep a separate repository checkout, run `npm`, or run Python manually.
The Skill launches the installed app/EXE; the app then starts its bundled local
backend executable.

macOS runtime:

```text
/Applications/Codeflow Light.app/Contents/MacOS/Codeflow Light
```

macOS bundled backend path:

```text
Codeflow Light.app/Contents/Resources/backend-bin/codeflow-light-backend
```

Windows runtime:

```text
CODEFLOW_LIGHT_APP_EXECUTABLE=<path to Codeflow-Light-0.1.0-x64.exe>
```

Windows bundled backend path inside the packaged app:

```text
resources/backend-bin/codeflow-light-backend.exe
```

If the packaged app is missing its bundled backend executable, it should be
rebuilt from the correct target OS. Do not fall back to repository-local backend
source for normal Skill usage.

For Windows portable releases, point the skill at the packaged EXE so the
plugin can launch it:

```powershell
setx CODEFLOW_LIGHT_APP_EXECUTABLE "C:\path\to\Codeflow-Light-0.1.0-x64.exe"
```

Use `CODEFLOW_LIGHT_SESSION_ID` when the caller provides a stable conversation
or task id. In Codex Desktop, the capture script automatically falls back to
`CODEX_THREAD_ID`, so parallel conversations open separate Codeflow windows and
each window shows only that conversation's groups. If no conversation id is
available, the app falls back to repository + branch grouping.

## Summary Quality

The backend does deterministic local summary only. To improve event nodes:

- Write `step_summary`, `step_detail`, and review notes in Korean.
- Set `agent` on each event so the flow shows which tool ran each phase,
  especially when implementation and review use different tools.
- Mention changed files in backticks, e.g. `frontend/src/pages/ChangePage.tsx`.
- Describe behavior and intent, not syntax trivia.
- Call out technical considerations such as state persistence, API contracts,
  diff boundaries, review gates, validation, and UI flow.
- Keep review findings and review-fix notes in distinct Korean paragraphs when possible.

## Constraints

- Do not call an external LLM API for Codeflow Light docs.
- Do not invent implementation or review details. Event summaries must describe
  the phase that just actually completed.
- Do not use Codeflow Light to generate line-by-line code comments. The app
  summarizes session steps and technical decisions instead.
- If event capture fails, still continue the implementation loop and briefly
  mention the local capture error in the final answer.
