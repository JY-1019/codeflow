import { Handle, Position, type NodeProps } from "@xyflow/react";
import type { ChangeNode } from "@/types/changes";

const STATUS_COLORS: Record<string, string> = {
  added: "border-emerald-400 bg-emerald-950/40",
  modified: "border-sky-400 bg-sky-950/40",
  deleted: "border-rose-400 bg-rose-950/40",
  renamed: "border-amber-400 bg-amber-950/40",
  unchanged: "border-slate-500 bg-slate-900/60",
};

const KIND_BADGE: Record<string, string> = {
  changed: "bg-sky-500/20 text-sky-200",
  affected: "bg-purple-500/20 text-purple-200",
  context: "bg-amber-500/20 text-amber-200",
  file: "bg-slate-500/20 text-slate-200",
};

export function ChangeNodeView({ data, selected }: NodeProps) {
  const node = data as unknown as ChangeNode & { kind: string };
  const statusClass = STATUS_COLORS[node.status] ?? STATUS_COLORS.unchanged;
  const badgeClass = KIND_BADGE[node.kind] ?? KIND_BADGE.changed;
  const ring = selected ? "ring-2 ring-sky-300" : "";
  return (
    <div
      className={`w-[280px] rounded-md border ${statusClass} ${ring} px-3 py-2 shadow-md`}
    >
      <Handle type="target" position={Position.Left} />
      <div className="flex items-center justify-between gap-2">
        <div className="truncate text-[13px] font-semibold text-slate-100">
          {node.label}
        </div>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${badgeClass}`}>
          {node.kind}
        </span>
      </div>
      <div className="mt-0.5 truncate text-[11px] text-slate-400">
        {node.file}
        {node.start_line ? `:${node.start_line}` : ""}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-1 text-[10px] text-slate-300">
        <span className="rounded bg-slate-700/60 px-1.5 py-0.5">
          {node.symbol_kind || "file"}
        </span>
        <span className="rounded bg-slate-700/60 px-1.5 py-0.5">
          {node.status}
        </span>
        {node.added_lines ? (
          <span className="text-emerald-300">+{node.added_lines}</span>
        ) : null}
        {node.removed_lines ? (
          <span className="text-rose-300">-{node.removed_lines}</span>
        ) : null}
      </div>
      {node.summary ? (
        <div className="mt-1.5 line-clamp-2 text-[11px] text-slate-300">
          {node.summary}
        </div>
      ) : null}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
