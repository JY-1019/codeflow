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
  | "referenced_by"
  | "contains"
  | "renamed_from";

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
}
