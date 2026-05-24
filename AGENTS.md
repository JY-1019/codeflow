# Codeflow Light Codex Instructions

These instructions refine the global review-first workflow for this repository.

## Scoped Review Guardrail

Codex `/review` can become slow when the uncommitted tree contains a whole
feature branch, generated output, dependency lockfile churn, or many untracked
files. Before asking for an uncommitted review in this repository:

1. Run a quick scope check:
   - `git diff --numstat`
   - `git ls-files --others --exclude-standard`
2. If the tracked diff is larger than roughly 1,500 changed lines, touches more
   than 15 files, or includes a large lockfile/generated-file change, split the
   review into logical slices instead of reviewing the whole working tree.
3. Prefer slice boundaries that match implementation units, for example:
   - backend services and tests
   - frontend components and types
   - Electron/skill capture scripts
   - dependency manifest and lockfile changes
4. For each slice, provide Codex only the relevant path-limited diff and any
   neighboring files needed for invariants. Avoid dumping full files unless the
   review actually needs full-file context.
5. Do not review generated lockfile diffs line by line. Treat files such as
   `frontend/package-lock.json` as review-excluded noise unless the dependency
   manifest changed. When `package.json` changes, review the manifest intent and
   only spot-check that the lockfile is synchronized, uses the expected package
   manager/registry, and does not introduce obviously unrelated packages.

Use full working-tree `/review` only when the diff is already small enough to be
read in one pass. The goal is still review-first quality; the repository-specific
rule is to keep each review unit small enough for a high-signal review.
