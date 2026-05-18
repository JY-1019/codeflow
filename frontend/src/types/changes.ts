export type ChangeStatus =
  | "added"
  | "modified"
  | "deleted"
  | "renamed"
  | "unchanged";

export type NodeKind = "changed" | "affected" | "context" | "file";

export type EdgeKind =
  | "modifies"
  | "calls"
  | "imports"
  | "referenced_by"
  | "contains"
  | "renamed_from";

export type ChangeSource = "working" | "staged" | "range" | "branch";

export interface ChangeNode {
  id: string;
  kind: NodeKind;
  label: string;
  file: string;
  language: string;
  symbol_kind: string;
  status: ChangeStatus;
  start_line: number | null;
  end_line: number | null;
  summary: string;
  body: string;
  snippet: string;
  added_lines: number;
  removed_lines: number;
}

export interface ChangeEdge {
  id: string;
  source: string;
  target: string;
  kind: EdgeKind;
  label: string;
  summary: string;
  body: string;
}

export interface ChangeGraphResponse {
  project_root: string;
  source: string;
  base_ref: string | null;
  head_ref: string | null;
  narrative: string;
  warnings: string[];
  nodes: ChangeNode[];
  edges: ChangeEdge[];
  assistant_response?: string;
}

export type ChangeGroupPhase =
  | "implementation"
  | "review"
  | "review_fix"
  | "verification"
  | "planning";

export interface TechnicalConsideration {
  label: string;
  detail: string;
}

export interface ChangeGroupSummary {
  implementation: string[];
  review: string[];
  technical_considerations: TechnicalConsideration[];
  changed_files: string[];
  file_count: number;
  edge_count: number;
  added_lines: number;
  removed_lines: number;
  workflow_run_count?: number;
  workflow_step_count?: number;
}

export type MarkdownWorkflowStepKind =
  | "preflight"
  | "markdown"
  | "branch"
  | "implementation"
  | "review"
  | "review_fix"
  | "verification"
  | "commit"
  | "push"
  | "merge";

export type MarkdownWorkflowStepStatus =
  | "completed"
  | "skipped"
  | "pending"
  | "blocked"
  | "unknown";

export interface MarkdownWorkflowStep {
  id: string;
  kind: MarkdownWorkflowStepKind;
  label: string;
  summary: string;
  detail: string;
  status: MarkdownWorkflowStepStatus;
  files: string[];
}

export interface MarkdownWorkflowRun {
  id: string;
  skill: string;
  skill_label: string;
  command_label: string;
  markdown_path: string;
  markdown_title: string;
  markdown_content: string;
  branch_name: string;
  status: "completed" | "in_progress" | "blocked";
  steps: MarkdownWorkflowStep[];
}

export interface ChangeGroup {
  id: string;
  sequence?: number;
  name: string;
  created_at: string;
  project_root: string;
  user_prompt: string;
  assistant_response: string;
  phase?: ChangeGroupPhase;
  phase_label?: string;
  summary?: ChangeGroupSummary;
  workflow_runs?: MarkdownWorkflowRun[];
  graph: ChangeGraphResponse;
}

export interface ChangeSessionSummary {
  total_groups: number;
  phase_counts: Partial<Record<ChangeGroupPhase, number>>;
  changed_files: string[];
  implementation: string[];
  review: string[];
  technical_considerations: TechnicalConsideration[];
  added_lines: number;
  removed_lines: number;
  workflow_run_count?: number;
  workflow_step_count?: number;
}

export interface ChangeSessionResponse {
  session_id: string | null;
  project_root: string;
  branch: string;
  groups: ChangeGroup[];
  latest_group_id: string | null;
  summary?: ChangeSessionSummary;
}

export interface CodexTokenUsage {
  input_tokens: number;
  cached_input_tokens: number;
  output_tokens: number;
  reasoning_output_tokens: number;
  total_tokens: number;
}

export interface CodexRateLimitWindow {
  used_percent: number | null;
  window_minutes: number | null;
  resets_at: number | null;
}

export interface CodexRateLimits {
  limit_id: string;
  limit_name: string | null;
  plan_type: string | null;
  rate_limit_reached_type: string | null;
  credits: unknown;
  primary: CodexRateLimitWindow | null;
  secondary: CodexRateLimitWindow | null;
}

export interface CodexCurrentSessionUsage {
  id: string;
  thread_name: string;
  cwd: string;
  updated_at: string | null;
  usage: CodexTokenUsage;
  rate_limits: CodexRateLimits | null;
}

export interface CodexUsageResponse {
  available: boolean;
  updated_at: string | null;
  scanned_sessions: number;
  all_time: CodexTokenUsage;
  current_session: CodexCurrentSessionUsage | null;
  rate_limits: CodexRateLimits | null;
  warnings: string[];
}
