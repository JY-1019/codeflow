---
name: codeflow
description: |
  Use this skill only when the user explicitly invokes Codeflow, for
  example with codeflow, /codeflow, or a direct request to open,
  show, or record Codeflow. It loads the canonical Codeflow capture
  instructions from this plugin and records implementation/review-loop events
  into the local desktop app.
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
