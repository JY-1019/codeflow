const AGENT_LABELS: Record<string, string> = {
  "claude-code": "Claude Code",
  claude: "Claude Code",
  codex: "Codex",
  "codex-cli": "Codex",
  "gpt-5": "Codex",
};

/**
 * Human-readable label for the tool/agent that performed a step.
 *
 * The backend already fills `agent_label`; this keeps the UI resilient when
 * only the raw `agent` slug is present (e.g. older captures).
 */
export function agentDisplayLabel(agent?: string, agentLabel?: string): string {
  const label = (agentLabel ?? "").trim();
  if (label) return label;
  const slug = (agent ?? "").trim().toLowerCase();
  if (!slug) return "";
  return (
    AGENT_LABELS[slug] ??
    slug
      .replace(/[-_]+/g, " ")
      .replace(/\b\w/g, (char) => char.toUpperCase())
  );
}
