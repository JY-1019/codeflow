---
name: codeflow-light
description: |
  Use this skill only when the user explicitly invokes Codeflow Light, for
  example with codeflow-light, /codeflow-light, or a direct request to open,
  show, or record Codeflow Light. It loads the canonical Codeflow Light capture
  instructions from this plugin and records implementation/review-loop events
  into the local desktop app.
---

# Codeflow Light Plugin Entry

Before taking task actions, read and follow the canonical instructions in
`../../skill/SKILL.md` completely. That file is shared by the standalone skill
install and by the Codex/Claude Code plugin manifests.

When the canonical instructions need the capture script, prefer the plugin PATH
wrapper if it is available:

```bash
SCRIPT="$(command -v codeflow-light-capture || true)"
[ -n "$SCRIPT" ] || SCRIPT="$HOME/.codex/skills/codeflow-light/scripts/codeflow_light_capture.py"
[ -f "$SCRIPT" ] || SCRIPT="$HOME/.claude/skills/codeflow-light/scripts/codeflow_light_capture.py"
```

The `codeflow` app launcher is also exposed through the plugin `bin/` directory
when the host supports plugin executables on PATH.
