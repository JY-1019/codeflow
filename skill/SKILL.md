---
name: codeflow
description: |
  Use this skill only when the user explicitly invokes Codeflow, for
  example with codeflow, /codeflow, or a direct request to open,
  show, or record Codeflow. Do not use it automatically for ordinary code
  changes, reviews, or Markdown Branch workflows unless the user also asks for
  Codeflow. It works the same from Claude Code and from Codex, and records
  which tool/agent performed each step, so a "Claude Code implements, then Codex
  review plugin reviews" loop (or an implement/review loop repeated entirely in
  Claude Code) stays traceable. When invoked on its own in a general request, it
  also records ad-hoc work as a general capture even without a fixed Markdown
  Branch format. It launches/focuses the local Codeflow desktop app and
  records implementation/review-loop events into the local backend. No LLM API
  is called by Codeflow.
---

# Codeflow

Codeflow is a local desktop app for visualizing one coding conversation as
a Markdown command and implementation/review flow. Each Codex/Claude
conversation gets its own desktop window and session history. Markdown Branch
Push/Commit workflows should be recorded as live events: Markdown command,
implementation, review, review-fix, verification, commit, and push/merge each
become concrete nodes as soon as that phase completes. User-facing event
summaries, review notes, status labels, and skill labels must be written in
Korean. Files are not the primary graph nodes; they are shown in the right
detail panel as raw deleted/added lines for implementation and review-fix nodes.
This skill does not install the desktop app or DMG. It only launches/focuses an
already installed Codeflow app and sends local capture events to it. If
commit, push, or merge are not part of the user's requested workflow, skip those
events or record them as skipped; implementation, review, review-fix, and
verification are enough for normal review-loop tracking.
The capture adapter requires Python 3.10 or newer and uses only the standard
library. The packaged app's backend is already bundled, so users do not need to
install backend Python packages or run `pip install`.
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

Only run the capture workflow after the user explicitly invokes Codeflow.
When this skill is explicitly used together with Markdown Branch Push/Commit, do
not wait for the final response to describe the whole loop. Pick one stable
`workflow_id` for the user's command and one stable `run_id` per Markdown file.
After each phase completes, run the capture script with `--event-kind`:

```bash
CAPTURE="$(command -v codeflow-capture || true)"
[ -n "$CAPTURE" ] || CAPTURE="$HOME/.codex/skills/codeflow/scripts/codeflow_capture.py"
[ -f "$CAPTURE" ] || CAPTURE="$HOME/.claude/skills/codeflow/scripts/codeflow_capture.py"

if [[ "$CAPTURE" == *.py ]]; then
  if command -v python3 >/dev/null 2>&1 && python3 -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
    CAPTURE_CMD=(python3 "$CAPTURE")
  elif command -v python >/dev/null 2>&1 && python -c 'import sys; raise SystemExit(sys.version_info < (3, 10))'; then
    CAPTURE_CMD=(python "$CAPTURE")
  else
    echo "Codeflow requires Python 3.10 or newer." >&2
    exit 1
  fi
else
  CAPTURE_CMD=("$CAPTURE")
fi
WORKFLOW_ID="markdown-review-$(date +%Y%m%d%H%M%S)"

"${CAPTURE_CMD[@]}" --project-root "$PWD" --event-kind markdown <<JSON
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
"${CAPTURE_CMD[@]}" --project-root "$PWD" --event-kind implementation <<JSON
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
"${CAPTURE_CMD[@]}" --project-root "$PWD" --event-kind review <<JSON
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
"${CAPTURE_CMD[@]}" --project-root "$PWD" --event-kind review_fix <<JSON
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
automatically. Set `agent` explicitly when phases use different tools. All four
implementation/review pairings are supported: Claude Code -> Codex, Codex ->
Codex, Claude Code -> Claude Code, and Codex -> Claude Code.

When a workflow crosses tool processes, every side must send the same
`session_id`, `workflow_id`, and `run_id`; set `CODEFLOW_SESSION_ID` or include
`session_id` in each payload. Without a shared session id, each host's own
conversation id intentionally opens a separate Codeflow session. Known agent
slugs (`claude-code`, `codex`) get friendly labels; any other slug is shown
as-is.

Record Git actions only after they actually succeed: `branch` after creating or
switching the work branch, then `commit`, `push`, and `merge` as applicable.
Set each Git event's `agent` to the tool that ran the command and include the
branch/ref or commit hash in `step_detail`. Stable ids keep repeated
implementation -> review -> review-fix loops and Git actions in one traceable
run with per-step actor badges.

## General capture (no fixed workflow)

When the user invokes Codeflow on its own in a general request that is not
a Markdown Branch workflow, still record what was done. Use `skill: "general"`
(or `skill: "codeflow"`), pick one `workflow_id` for the request and one
`run_id` for the unit of work, set `command_label` to a short Korean title, and
emit `implementation` / `review` / `verification` events as each part of the
work completes:

```bash
WORKFLOW_ID="codeflow-general-$(date +%Y%m%d%H%M%S)"
"${CAPTURE_CMD[@]}" --project-root "$PWD" --event-kind implementation <<JSON
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

Repeat the capture-command resolution at the start of each separate shell
invocation; shell variables do not carry across tool calls.

The examples above use a POSIX shell. On Windows PowerShell, invoke the same
installed script with the Python launcher instead:

```powershell
'{"workflow_id":"<id>","run_id":"<id>","step_summary":"<요약>"}' |
  py -3 "$env:USERPROFILE\.codex\skills\codeflow\scripts\codeflow_capture.py" `
    --project-root "$PWD" --event-kind implementation
```

Use `python` instead of `py -3` when that is the available Python 3.10+
command. Marketplace-installed Claude plugins use the `codeflow-capture`
command from the plugin's Bash PATH.

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
   `/Applications/Codeflow.app/Contents/MacOS/Codeflow` on macOS,
   or the path in `CODEFLOW_APP_EXECUTABLE` for a portable/installed
   Windows EXE.
3. Start or focus the app window for the current conversation/session.
4. Wait for the local FastAPI backend.
5. POST event payloads to `/api/sessions/event`. Legacy final-turn payloads
   without `--event-kind` still POST to `/api/sessions/capture`.

Do not use repository-local `npm` or Python launch paths for normal usage. The
installed DMG/EXE is the runtime surface. This skill must not try to download
or install a DMG/EXE on the user's behalf. The repository-local development
fallback is available only when `CODEFLOW_ALLOW_DEV_LAUNCH=1` is
explicitly set for local development.

The capture script looks for `CODEFLOW_EXECUTABLE` first, then the
bundled `bin/codeflow` executable. Use this when testing the desktop app
directly:

```bash
$HOME/.codex/skills/codeflow/bin/codeflow --project-root "$PWD"
```

## Packaged App Runtime

The macOS DMG and Windows EXE are the normal runtime targets for this skill. The
packaged app must run the monitoring UI and local backend without requiring the
user to keep a separate repository checkout, run `npm`, or run Python manually.
The Skill launches the installed app/EXE; the app then starts its bundled local
backend executable.

macOS runtime:

```text
/Applications/Codeflow.app/Contents/MacOS/Codeflow
```

macOS bundled backend path:

```text
Codeflow.app/Contents/Resources/backend-bin/codeflow-backend
```

Windows runtime:

```text
CODEFLOW_APP_EXECUTABLE=<path to Codeflow-0.1.0-x64.exe>
```

Windows bundled backend path inside the packaged app:

```text
resources/backend-bin/codeflow-backend.exe
```

If the packaged app is missing its bundled backend executable, it should be
rebuilt from the correct target OS. Do not fall back to repository-local backend
source for normal Skill usage.

For Windows portable releases, point the skill at the packaged EXE so the
plugin can launch it:

```powershell
setx CODEFLOW_APP_EXECUTABLE "C:\path\to\Codeflow-0.1.0-x64.exe"
```

Use `CODEFLOW_SESSION_ID` when the caller provides a stable conversation or
task id, and always share it across a Codex/Claude Code handoff. In Codex
Desktop, the capture script automatically falls back to
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

- Do not call an external LLM API for Codeflow docs.
- Do not invent implementation or review details. Event summaries must describe
  the phase that just actually completed.
- Do not use Codeflow to generate line-by-line code comments. The app
  summarizes session steps and technical decisions instead.
- If event capture fails, still continue the implementation loop and briefly
  mention the local capture error in the final answer.
