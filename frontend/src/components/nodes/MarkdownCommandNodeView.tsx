import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import { BookOpenText, GitBranch, Route } from "lucide-react";
import type { MarkdownWorkflowRun } from "@/types/changes";

export interface MarkdownCommandNodeData extends MarkdownWorkflowRun {
  groupId: string;
  groupName: string;
}

export const MarkdownCommandNodeView = memo(({ data, selected }: NodeProps) => {
  const run = data as unknown as MarkdownCommandNodeData;
  const title = run.markdown_title || run.markdown_path || "현재 요청";
  const markdownPreview = firstContentLine(run.markdown_content) || run.markdown_path || "Markdown 원문 대기";

  return (
    <div
      className={`relative w-[320px] rounded-md border bg-slate-900 shadow-lg transition ${
        selected ? "border-cyan-300 ring-2 ring-cyan-300/30" : "border-sky-500/70"
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className="!h-3 !w-3 !border-2 !border-slate-950 !bg-sky-300"
      />
      <div className="border-b border-slate-700/80 bg-sky-950/30 px-3 py-2">
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sky-200">
            <Route className="h-3 w-3" />
            {run.skill_label || run.skill}
          </span>
          <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-slate-300">
            {run.status === "completed" ? "완료" : run.status === "blocked" ? "차단" : "진행"}
          </span>
        </div>
        <div className="mt-2 line-clamp-2 text-[13px] font-semibold leading-snug text-slate-100">
          {title}
        </div>
        {run.markdown_path ? (
          <div className="mt-1 truncate font-mono text-[10px] text-slate-400" title={run.markdown_path}>
            {run.markdown_path}
          </div>
        ) : null}
      </div>
      <div className="space-y-2 px-3 py-2 text-[11px] text-slate-300">
        <div className="line-clamp-2 leading-snug text-slate-400">{markdownPreview}</div>
        <div className="flex items-center justify-between gap-2">
          <span className="inline-flex items-center gap-1.5 text-slate-400">
            <BookOpenText className="h-3.5 w-3.5 text-sky-300" />
            {run.steps?.length ?? 0} steps
          </span>
          {run.branch_name ? (
            <span className="inline-flex min-w-0 items-center gap-1.5 text-slate-400">
              <GitBranch className="h-3.5 w-3.5 shrink-0 text-slate-500" />
              <span className="truncate font-mono text-[10px]" title={run.branch_name}>
                {run.branch_name}
              </span>
            </span>
          ) : null}
        </div>
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className="!h-3 !w-3 !border-2 !border-slate-950 !bg-sky-300"
      />
    </div>
  );
});

MarkdownCommandNodeView.displayName = "MarkdownCommandNodeView";

function firstContentLine(content: string): string {
  return content
    .split("\n")
    .map((line) => line.trim())
    .find(Boolean) ?? "";
}
