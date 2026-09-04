---
name: codeflow
description: |
  Never select Codeflow inside `/review`, `codex review`, `/codex:review`, or
  another dedicated reviewer subtask; return findings directly there.
  Use Codeflow for repository work that benefits from implementation, review,
  verification, or Git integration, whether or not the user names Codeflow or
  uses a special prompt format. It orchestrates a parallel-first implementation
  and review loop, uses Codex's dedicated built-in reviewer from Codex or Claude
  Code when available and a separate same-platform reviewer otherwise, isolates
  explicitly requested Git work in worktrees, records each completed phase in
  the local Codeflow app, and returns one synthesized report. No LLM API is
  called by the Codeflow app itself.
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

## Mandatory Orchestration

Before applying any other rule in this file, check whether the host launched a
dedicated built-in review session through `/review`, `codex review`,
`/codex:review`, or a parent marked the task `CODEFLOW_TERMINAL_REVIEW=1`. That
context is already the terminal reviewer:
inspect the requested change and return findings directly. Do not run the
remaining orchestration or capture workflow, invoke or spawn another reviewer,
modify files, or emit events. The parent context owns fixes and synthesis. A
top-level user request to review or record work is not a terminal subtask and
must still use the workflow and capture its review.

When the user explicitly selects a more-specific execution Skill, that Skill
owns its implementation-unit boundaries, model and effort, Git/worktree policy,
and review interface. Codeflow supplies capture and synthesis, and fills only
orchestration defaults the specific Skill or user did not set. Direct user
instructions always take precedence.

Apply this workflow to every repository task handled after Codeflow is selected,
regardless of how the user phrases the request. A host may select Skills by
semantic relevance rather than on every arbitrary prompt, so an explicit
`codeflow`, `$codeflow`, or `/codeflow:codeflow` invocation remains the reliable
way to force activation.

1. Before editing, inspect the request, repository state, independent work
   units, write-set overlap, dependencies, available reviewer capabilities, and
   whether the user explicitly requested Git state changes. For each unit,
   snapshot every planned write path outside the repository before its first
   edit, including whether the path was absent. Snapshot any newly discovered
   write path before touching it. Use those snapshots to produce the exact unit
   patch after implementation.
2. Run independent read-only discovery in parallel. Run independent writes in
   parallel only when their file ownership does not overlap and each write runs
   in an isolated worktree; otherwise serialize them. Do not parallelize a step
   before its dependency is complete.
3. Use the latest-generation balanced implementation model with slightly lower
   token use when model selection is available:
   - Codex: the newest `terra` model, currently `gpt-5.6-terra`, at medium
     reasoning effort.
   - Claude Code: the evergreen `sonnet` alias, currently Claude Sonnet 5 on the
     Anthropic API, at medium effort.
   If the model is unavailable or the host cannot override the active model,
   inherit the current model, continue, and mention the fallback in the final
   report.
4. Every changed source, configuration, test, or documentation unit must pass
   `implementation -> review -> review_fix (when needed) -> review again ->
   verification`. If verification fails, fix the failure and repeat review and
   verification. Continue until no actionable review findings remain and focused
   verification passes, or report a genuine blocker.
5. Use the host's dedicated internal reviewer agent when it exists. A command is
   only the transport into that reviewer; do not count a generic Codex call,
   generic subagent prompt, or the implementation agent's self-review as the
   review gate. Review correctness, regressions, edge cases, public API
   compatibility, missing tests, unnecessary complexity, and unrelated edits.
   Scope the reviewer to the exact unit patch and its neighboring context. When
   the working tree had pre-existing changes, give the reviewer the snapshot
   path, unit patch path, and allowed file list; explicitly exclude baseline
   hunks and all other working-tree changes. Apply fixes only inside that unit
   scope. Never let `--uncommitted` turn unrelated user-owned edits into review
   findings or fix targets.
   Exclude generated, vendored, lock, build, and binary artifacts unless the
   artifact itself is the requested product. A reviewer is a terminal subtask:
   return findings without selecting Codeflow again, spawning another reviewer,
   modifying files, or emitting capture events. Mark any explicitly spawned
   fallback reviewer task with `CODEFLOW_TERMINAL_REVIEW=1`.
6. Route review by platform:
   - Claude Code: for an automatic working-tree loop, run the model-callable
     `codex review --uncommitted` CLI with review instructions limited to the
     saved unit patch, which starts Codex's dedicated reviewer;
     use `--base <ref>` or `--commit <sha>` instead when that is the requested
     review target. An equivalent model-callable plugin capability is also
     valid. `/codex:review --wait` reaches the same shared reviewer when the
     user invokes it, but a Skill cannot invoke that user-only slash command.
     Do not substitute `codex exec`, a generic Codex prompt, or an arbitrary
     Codex subtask. The parent Claude workflow owns fixes, re-review, and
     synthesis; do not silently enable a persistent Codex stop gate. If the
     built-in reviewer is unavailable or fails, use a separate Claude reviewer
     context at `sonnet` high effort. Record the actual reviewer as `codex` or
     `claude-code`.
   - Codex-only: use native `/review` or `codex review`; both start Codex's
     dedicated reviewer. Keep implementation, review-fix, and verification
     inside Codex; never require Claude or replace the review gate with the
     implementation agent's self-review.
   - Claude-only: use separate Claude implementation and review contexts; never
     skip review because Codex is unavailable.

For a shared or pre-dirty working tree, invoke the dedicated reviewer with an
explicit unit boundary such as:

```bash
codex review --uncommitted "Review only the implementation-unit patch at $UNIT_PATCH for $UNIT_FILES. Compare it with snapshots at $UNIT_BASELINE. Ignore and do not propose fixes for every pre-existing or out-of-scope change."
```

The patch and snapshots must be outside the repository and readable by the
reviewer. A clean isolated worktree may use the target flag without this extra
baseline instruction because its uncommitted diff is already the unit boundary.
7. Git state changes require explicit user authorization. A request to commit,
   push, merge, or reflect changes into a branch authorizes only those named
   operations. For new authorized implementation work, create one branch and
   isolated worktree per independent unit before editing, preserve the user's
   existing worktree, and serialize integration and push. A request only to
   commit, push, or merge existing changes or a current/named branch stays on
   that state and must not create a replacement worktree. Without an authorized
   Git request, do not create worktrees, branches, commits, pushes, or merges.
8. The coordinator alone returns the final response. Wait for every parallel
   unit, reconcile conflicts and duplicated findings, and synthesize one concise
   report covering outcome, review fixes, verification, Git result, model
   fallbacks, blockers, and remaining risks. Do not concatenate worker reports.

For read-only questions or diagnostics, treat the work product as the analysis
or report: gather independent evidence in parallel where useful, review the
evidence and conclusions, verify citations or commands, and return one synthesis.
Do not invent code changes or Git events for a read-only task.

## Capture Workflow

Run the capture workflow whenever Codeflow is active. When it is used together
with Markdown Branch Push/Commit, do not wait for the final response to describe
the whole loop. Pick one stable
`workflow_id` for the user's command and one stable `run_id` per Markdown file.
Record `preflight` after partitioning the work, then record each phase only after
it actually completes. Use one `run_id` per parallel unit:

Resolve the primary repository's canonical root and choose one explicit
`CODEFLOW_SESSION_ID` shared by every lane. The coordinator alone emits events;
workers report their phase, absolute worktree path, refs, files, and results.
Before any worker event, emit one coordinator `preflight` from `CANONICAL_ROOT`;
this opens the session window on a path that will not be deleted. After an
authorized worktree is created, set that lane's `DIFF_ROOT` to its exact path
and emit its `preflight` there before editing; serial runs use the canonical
root. Never change `project_root` within a run: keep implementation, review,
review-fix, verification, commit, and push events for that lane on the same
`DIFF_ROOT`. Canonical integration uses the coordinator run or a new integration
`run_id`. After all lanes finish, emit the coordinator's final `verification`
from `CANONICAL_ROOT` before removing worktrees. This avoids cross-worktree diff
baselines and leaves both the persisted session and window on a stable path in
the packaged 0.1 app.

```bash
CANONICAL_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)"
DIFF_ROOT="${CODEFLOW_DIFF_ROOT:-$CANONICAL_ROOT}"
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
COORDINATOR_RUN_ID="coordinator"
RUN_ID="<stable id for this markdown file>"
PRIMARY_BRANCH="$(git -C "$CANONICAL_ROOT" branch --show-current 2>/dev/null || true)"
export CODEFLOW_SESSION_ID="${CODEFLOW_SESSION_ID:-${CODEX_THREAD_ID:-${CODEX_SESSION_ID:-${CLAUDECODE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-repo:$CANONICAL_ROOT:${PRIMARY_BRANCH:-worktree}}}}}}"

# Emit this coordinator event once, before any worktree-backed event.
"${CAPTURE_CMD[@]}" --session-id "$CODEFLOW_SESSION_ID" --project-root "$CANONICAL_ROOT" --event-kind preflight <<JSON
{
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "$COORDINATOR_RUN_ID",
  "command_label": "<전체 작업의 한국어 제목>",
  "step_summary": "작업 단위와 병렬 실행 계획을 확인했습니다.",
  "step_detail": "<reviewer availability, dependencies, and lane plan>",
  "source": "working"
}
JSON

"${CAPTURE_CMD[@]}" --session-id "$CODEFLOW_SESSION_ID" --project-root "$DIFF_ROOT" --event-kind preflight <<JSON
{
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "$RUN_ID",
  "skill": "markdown-branch-commit",
  "command_label": "<markdown title or file name>",
  "step_summary": "의존성과 리뷰 경로, 병렬 실행 가능 여부를 확인했습니다.",
  "step_detail": "<reviewer availability, dependencies, and lane decision>",
  "source": "branch"
}
JSON

"${CAPTURE_CMD[@]}" --session-id "$CODEFLOW_SESSION_ID" --project-root "$DIFF_ROOT" --event-kind markdown <<JSON
{
  "user_prompt": "<copy the user's latest request>",
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "$RUN_ID",
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

Use the same session, workflow, and run ids for later events in that Markdown
file. At the start of every separate capture shell, repeat capture-command
resolution and assign the same literal `CODEFLOW_SESSION_ID`, `WORKFLOW_ID`, and
`CANONICAL_ROOT` and `DIFF_ROOT`; never rely on a previous shell's export:

```bash
CODEFLOW_SESSION_ID="<same stable session id>"
WORKFLOW_ID="<same stable workflow id>"
CANONICAL_ROOT="<same canonical repository root>"
DIFF_ROOT="<absolute worktree path reported for this run>"
"${CAPTURE_CMD[@]}" --session-id "$CODEFLOW_SESSION_ID" --project-root "$DIFF_ROOT" --event-kind implementation <<JSON
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
"${CAPTURE_CMD[@]}" --session-id "$CODEFLOW_SESSION_ID" --project-root "$DIFF_ROOT" --event-kind review <<JSON
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
"${CAPTURE_CMD[@]}" --session-id "$CODEFLOW_SESSION_ID" --project-root "$DIFF_ROOT" --event-kind review_fix <<JSON
{
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "<stable id for this markdown file>",
  "step_summary": "<리뷰를 어떻게 반영했는지 한국어로 요약>",
  "step_detail": "<구체적인 수정 내용을 한국어로 설명>",
  "source": "branch"
}
JSON
```

Capture a lane's `verification`, `commit`, and `push` from that lane's unchanged
`DIFF_ROOT`. Capture canonical `merge` or other integration work under the
coordinator run or a new integration `run_id`; never reuse a worker run after
changing roots. If a commit hook, conflict resolution, remote update, or
integration changes files afterward, use a new integration `run_id` on that
exact root and repeat `preflight -> implementation/review_fix -> review ->
verification` before finalizing. End with a coordinator `verification` on
`CANONICAL_ROOT`, using the same source as its initial preflight, before deleting
worktrees. Use
`step_status: "skipped"` when a phase is intentionally not run, and
`step_status: "blocked"` when the loop stops on a blocker.

## Cross-tool tracking (Claude Code + Codex)

Each event accepts an `agent` field naming the tool that performed that step.
When omitted, the capture script infers the host tool from the environment
(`claude-code` or `codex`). Set `agent` explicitly when phases use different
tools. In Claude Code, use the Codex plugin's built-in reviewer path when it is
callable and fall back to a separate Claude reviewer otherwise. In Codex-only
environments, use Codex's dedicated reviewer. Never label a generic Codex call
or implementation-agent self-review as a Codex review.

When a workflow crosses tool processes, every side must send the same
`session_id` and `workflow_id`; actors working on the same unit must also share
that unit's `run_id`, while parallel units keep distinct run ids. Pass the
chosen session id explicitly in every capture invocation with `--session-id` or
in its payload. Without it, each host's own conversation id intentionally opens
a separate Codeflow session. Known agent slugs (`claude-code`, `codex`) get
friendly labels; any other slug is shown as-is.

Record Git actions only after they actually succeed: `branch` after creating the
isolated worktree and work branch, then `commit`, `push`, and `merge` as
authorized.
Set each Git event's `agent` to the tool that ran the command and include the
branch/ref or commit hash in `step_detail`. Stable ids keep repeated
implementation -> review -> review-fix loops and Git actions in one traceable
run with per-step actor badges.

## General capture (no fixed workflow)

For a general request that is not a Markdown Branch workflow, record what was
done. Use `skill: "general"`
(or `skill: "codeflow"`), pick one `workflow_id` for the request and one
`run_id` for the unit of work, set `command_label` to a short Korean title, and
emit `implementation` / `review` / `verification` events as each part of the
work completes:

```bash
CANONICAL_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd -P)"
DIFF_ROOT="${CODEFLOW_DIFF_ROOT:-$CANONICAL_ROOT}"
WORKFLOW_ID="codeflow-general-$(date +%Y%m%d%H%M%S)"
RUN_ID="ad-hoc"
PRIMARY_BRANCH="$(git -C "$CANONICAL_ROOT" branch --show-current 2>/dev/null || true)"
export CODEFLOW_SESSION_ID="${CODEFLOW_SESSION_ID:-${CODEX_THREAD_ID:-${CODEX_SESSION_ID:-${CLAUDECODE_SESSION_ID:-${CLAUDE_CODE_SESSION_ID:-repo:$CANONICAL_ROOT:${PRIMARY_BRANCH:-worktree}}}}}}"
"${CAPTURE_CMD[@]}" --session-id "$CODEFLOW_SESSION_ID" --project-root "$DIFF_ROOT" --event-kind preflight <<JSON
{
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "$RUN_ID",
  "skill": "general",
  "command_label": "<무엇을 할지 한국어 제목>",
  "step_summary": "의존성과 리뷰 경로, 병렬 실행 가능 여부를 확인했습니다.",
  "step_detail": "<reviewer availability, dependencies, and lane decision>",
  "source": "working"
}
JSON

"${CAPTURE_CMD[@]}" --session-id "$CODEFLOW_SESSION_ID" --project-root "$DIFF_ROOT" --event-kind implementation <<JSON
{
  "workflow_id": "$WORKFLOW_ID",
  "run_id": "$RUN_ID",
  "skill": "general",
  "command_label": "<무엇을 했는지 한국어 제목>",
  "step_summary": "<한국어로 작업 요약>",
  "step_detail": "<한국어로 세부 내용>",
  "source": "working"
}
JSON
```

Repeat the capture-command resolution and re-declare the same literal session,
workflow, run, and diff-root values at the start of each separate shell
invocation; shell variables do not carry across tool calls.

The examples above use a POSIX shell. On Windows PowerShell, invoke the same
installed script with the Python launcher instead:

```powershell
$workflowId = "<same stable workflow id>"
$diffRoot = "<absolute worker worktree path, or canonical root for serial work>"
if (-not $env:CODEFLOW_SESSION_ID) {
  $canonicalRoot = (git rev-parse --show-toplevel 2>$null)
  if (-not $canonicalRoot) { $canonicalRoot = (Get-Location).Path }
  $primaryBranch = (git -C $canonicalRoot branch --show-current 2>$null)
  if (-not $primaryBranch) { $primaryBranch = "worktree" }
  $env:CODEFLOW_SESSION_ID = @(
    $env:CODEX_THREAD_ID, $env:CODEX_SESSION_ID,
    $env:CLAUDECODE_SESSION_ID, $env:CLAUDE_CODE_SESSION_ID,
    "repo:$canonicalRoot`:$primaryBranch"
  ) | Where-Object { $_ } | Select-Object -First 1
}
@{ workflow_id = $workflowId; run_id = "<id>"; step_summary = "<요약>" } |
  ConvertTo-Json -Compress |
  py -3 "$env:USERPROFILE\.codex\skills\codeflow\scripts\codeflow_capture.py" `
    --session-id "$env:CODEFLOW_SESSION_ID" --project-root "$diffRoot" --event-kind implementation
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
CODEFLOW_APP_EXECUTABLE=<path to Codeflow-0.2.1-x64.exe>
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
setx CODEFLOW_APP_EXECUTABLE "C:\path\to\Codeflow-0.2.1-x64.exe"
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
