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
SCRIPT="$(command -v codeflow-capture || true)"
[ -n "$SCRIPT" ] || SCRIPT="$HOME/.codex/skills/codeflow/scripts/codeflow_capture.py"
[ -f "$SCRIPT" ] || SCRIPT="$HOME/.claude/skills/codeflow/scripts/codeflow_capture.py"
```

The `codeflow` app launcher is also exposed through the plugin `bin/` directory
when the host supports plugin executables on PATH.
