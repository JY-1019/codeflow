import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Book, Code, Plus, Minus, FileText, Box, Component, Layers } from "lucide-react";
import type { ChangeNode } from "@/types/changes";

/**
 * Per-kind base style (used when status is "unchanged" or when we want to
 * show *what kind* of node this is).
 */
const KIND_CONFIG: Record<
  string,
  { label: string; color: string; icon: string }
> = {
  changed: { label: "변경", color: "#60a5fa", icon: "✎" },
  affected: { label: "영향", color: "#a855f7", icon: "↘" },
  context: { label: "맥락", color: "#f59e0b", icon: "✦" },
  file: { label: "파일", color: "#94a3b8", icon: "▣" },
};

/**
 * Diff-status color override (matches original codeflow CustomNodes.tsx).
 */
const STATUS_COLOR: Record<string, { color: string; opacity?: number }> = {
  added: { color: "#4ade80" },
  modified: { color: "#60a5fa" },
  deleted: { color: "#f87171", opacity: 0.7 },
  renamed: { color: "#fb923c" },
  unchanged: { color: "#64748b" },
};

const SYMBOL_KIND_ICON: Record<string, typeof FileText> = {
  file: FileText,
  function: Component,
  method: Component,
  class: Box,
  module: Layers,
};

interface ChangeNodeData extends ChangeNode {
  hasBody?: boolean;
}

export const ChangeNodeView = memo(({ data, selected }: NodeProps) => {
  const node = data as unknown as ChangeNodeData;
  const kindConfig = KIND_CONFIG[node.kind] ?? KIND_CONFIG.changed;
  const statusEntry = STATUS_COLOR[node.status] ?? STATUS_COLOR.unchanged;

  // status takes precedence over kind for the border/glow (matches codeflow)
  const statusColor = node.status === "unchanged" ? kindConfig.color : statusEntry.color;
  const boxShadow = `0 0 10px ${statusColor}40`;
  const opacity = statusEntry.opacity ?? 1;

  const SymbolIcon = SYMBOL_KIND_ICON[node.symbol_kind] ?? FileText;
  const hasBody = Boolean(node.body && node.body.trim());
  const hasSnippet = Boolean(node.snippet && node.snippet.trim());

  return (
    <div
      className={`relative min-w-[220px] rounded-lg border-2 shadow-lg transition-all duration-200 ${
        selected ? "scale-[1.03] ring-2 ring-white/50" : ""
      }`}
      style={{
        backgroundColor: "#1e293b",
        borderColor: statusColor,
        boxShadow,
        opacity,
      }}
    >
      <Handle
        id="left"
        type="target"
        position={Position.Left}
        className="!h-3.5 !w-3.5 !border-2 !border-white transition-transform hover:!scale-125"
        style={{ backgroundColor: statusColor }}
      />

      <div
        className="flex items-center justify-between gap-2 rounded-t-md px-3 py-1.5"
        style={{ backgroundColor: `${kindConfig.color}30` }}
      >
        <div className="flex items-center gap-1.5">
          <span className="text-[13px] leading-none" style={{ color: kindConfig.color }}>
            {kindConfig.icon}
          </span>
          <span
            className="text-[10px] font-semibold uppercase tracking-wider"
            style={{ color: kindConfig.color }}
          >
            {kindConfig.label}
          </span>
          <span className="rounded bg-slate-900/60 px-1.5 py-0.5 text-[9px] uppercase text-slate-300">
            {symbolKindLabel(node.symbol_kind)}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-[10px]">
          {node.added_lines ? (
            <span className="inline-flex items-center gap-0.5 text-emerald-300">
              <Plus className="h-2.5 w-2.5" />
              {node.added_lines}
            </span>
          ) : null}
          {node.removed_lines ? (
            <span className="inline-flex items-center gap-0.5 text-rose-300">
              <Minus className="h-2.5 w-2.5" />
              {node.removed_lines}
            </span>
          ) : null}
          <span
            className="rounded px-1.5 py-0.5 font-medium uppercase tracking-wider"
            style={{
              backgroundColor: `${statusColor}25`,
              color: statusColor,
            }}
          >
            {statusLabel(node.status)}
          </span>
        </div>
      </div>

      <div className="px-3 py-2">
        <div className="flex items-center gap-1.5">
          <SymbolIcon className="h-3 w-3 shrink-0 text-slate-400" />
          <div
            className="truncate text-[13px] font-medium"
            style={{ color: statusColor }}
            title={node.label}
          >
            {node.label}
          </div>
        </div>
        <div className="mt-0.5 truncate text-[11px] text-slate-400" title={node.file}>
          {node.file}
        </div>
        {node.summary ? (
          <div className="mt-1.5 line-clamp-2 text-[11px] text-slate-300">{node.summary}</div>
        ) : null}
      </div>

      <div className="flex gap-1 border-t border-slate-600/60 px-3 py-1.5">
        <button
          className={`flex flex-1 items-center justify-center gap-1 rounded px-2 py-1 text-[10px] transition-colors ${
            hasBody
              ? "bg-purple-600/25 text-purple-300"
              : "bg-slate-700/50 text-slate-500"
          }`}
          title={hasBody ? "AI 응답에서 매핑된 설명 있음" : "매핑된 설명 없음"}
        >
          <Book className="h-3 w-3" />
          설명
        </button>
        <button
          className={`flex flex-1 items-center justify-center gap-1 rounded px-2 py-1 text-[10px] transition-colors ${
            hasSnippet
              ? "bg-emerald-600/25 text-emerald-300"
              : "bg-slate-700/50 text-slate-500"
          }`}
          title={hasSnippet ? "diff snippet 있음" : "snippet 없음"}
        >
          <Code className="h-3 w-3" />
          Diff
        </button>
      </div>

      <Handle
        id="right"
        type="source"
        position={Position.Right}
        className="!h-3.5 !w-3.5 !border-2 !border-white transition-transform hover:!scale-125"
        style={{ backgroundColor: statusColor }}
      />
    </div>
  );
});

ChangeNodeView.displayName = "ChangeNodeView";

function symbolKindLabel(kind: string): string {
  if (kind === "file") return "파일";
  if (kind === "function") return "함수";
  if (kind === "method") return "메서드";
  if (kind === "class") return "클래스";
  if (kind === "module") return "모듈";
  return kind || "파일";
}

function statusLabel(status: string): string {
  if (status === "added") return "추가";
  if (status === "modified") return "수정";
  if (status === "deleted") return "삭제";
  if (status === "renamed") return "이름 변경";
  if (status === "unchanged") return "변경 없음";
  return status || "변경";
}
