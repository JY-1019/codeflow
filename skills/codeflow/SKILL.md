---
name: codeflow
description: |
  Never select Codeflow inside `/review`, `codex review`, `/codex:review`, or
  another dedicated reviewer subtask; return findings directly there.
  Use Codeflow for repository implementation, review, verification, and Git
  integration work whether or not the user names Codeflow or uses a special
  prompt format. It loads the canonical parallel-first orchestration and review
  loop, records completed phases in the local desktop app, and returns one
  synthesized report.
---

# Codeflow Plugin Entry

Before taking task actions, read and follow the canonical instructions in
`../../skill/SKILL.md` completely. That file is shared by the standalone skill
install and by the Codex/Claude Code plugin manifests.

When the canonical instructions need the capture script, prefer the plugin PATH
wrapper if it is available:

```bash
CAPTURE="$(command -v codeflow-capture || true)"
```

The plugin exposes both `codeflow-capture` and `codeflow` through its `bin/`
directory. If `codeflow-capture` is not on PATH, follow the standalone fallback
in the canonical instructions; do not require installed Skill files to retain
their executable bit.

The capture adapter requires Python 3.10 or newer. It uses only the Python
standard library; the packaged desktop app already contains its backend and
does not require a separate Python runtime.
