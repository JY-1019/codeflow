import { memo, useLayoutEffect, useRef, useState } from "react";
import { Handle, NodeToolbar, Position, type NodeProps } from "@xyflow/react";
import {
  Bot,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  CircleDashed,
  ClipboardList,
  Code2,
  FileText,
  GitBranch,
  GitCommitHorizontal,
  GitMerge,
  GitPullRequestArrow,
  SearchCheck,
  SkipForward,
  Wrench,
  XCircle,
  type LucideIcon,
} from "lucide-react";
import { agentDisplayLabel } from "@/flow/utils/agentLabel";
import type { MarkdownWorkflowStep, MarkdownWorkflowStepStatus } from "@/types/changes";

export interface WorkflowStepNodeData extends MarkdownWorkflowStep {
  groupId: string;
  runId: string;
  runTitle?: string;
  markdownPath?: string;
  branchName?: string;
  skillLabel?: string;
}

export const WorkflowStepNodeView = memo(({ data, selected }: NodeProps) => {
  const step = data as unknown as WorkflowStepNodeData;
  const phase = phaseConfig(step.kind);
  const StatusIcon = statusIcon(step.status);
  const StepIcon = phase.icon;
  const agentLabel = agentDisplayLabel(step.agent, step.agent_label);
  const summaryRef = useRef<HTMLDivElement>(null);
  const [summaryExpanded, setSummaryExpanded] = useState(false);
  const [summaryOverflows, setSummaryOverflows] = useState(false);

  useLayoutEffect(() => {
    const summary = summaryRef.current;
    if (!summary) return;
    const collapsedHeight = Math.ceil(Number.parseFloat(getComputedStyle(summary).lineHeight) * 3);
    const overflows = summary.scrollHeight > collapsedHeight;
    setSummaryOverflows(overflows);
    if (!overflows) setSummaryExpanded(false);
  }, [step.summary]);

  return (
    <div
      className={`relative w-[228px] rounded-md border bg-slate-900 shadow-lg transition ${
        selected ? `${phase.selectedBorder} ring-2 ${phase.ring}` : phase.border
      }`}
    >
      <NodeToolbar
        isVisible={summaryExpanded}
        position={Position.Bottom}
        align="start"
        offset={8}
        className="nopan nokey w-[228px] rounded-md border border-cyan-400/60 bg-slate-900 p-3 shadow-xl"
      >
        <div
          className="nowheel nopan nokey max-h-48 overflow-y-auto whitespace-pre-wrap break-all text-[12px] leading-snug text-slate-200"
          tabIndex={0}
          aria-label="Expanded summary"
        >
          {step.summary}
        </div>
      </NodeToolbar>
      <Handle
        type="target"
        position={Position.Left}
        className={`!h-3 !w-3 !border-2 !border-slate-950 ${phase.handle}`}
      />
      <div className={`border-b border-slate-700/80 px-3 py-2 ${phase.header}`}>
        <div className="flex items-center justify-between gap-2">
          <span className={`inline-flex min-w-0 items-center gap-1.5 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${phase.badge}`}>
            <StepIcon className="h-3 w-3" />
            <span className="truncate">{stepKindLabel(step.kind)}</span>
          </span>
          <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ${statusClass(step.status)}`}>
            <StatusIcon className="h-3 w-3" />
            {statusLabel(step.status)}
          </span>
        </div>
        <div className="mt-1 flex items-center justify-between gap-2">
          <span className="min-w-0 truncate text-[10px] text-slate-400" title={step.runTitle || step.label}>
            {step.runTitle || step.label}
          </span>
          {agentLabel ? (
            <span
              className="inline-flex shrink-0 items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300"
              title={`Agent: ${agentLabel}`}
            >
              <Bot className="h-3 w-3" />
              <span className="max-w-[84px] truncate">{agentLabel}</span>
            </span>
          ) : null}
        </div>
      </div>
      <div className="px-3 py-2">
        <div className="mb-1 truncate text-[12px] font-semibold text-slate-100" title={step.label}>
          {step.label}
        </div>
        <div
          ref={summaryRef}
          className="line-clamp-3 min-h-[48px] break-all text-[12px] leading-snug text-slate-200"
        >
          {step.summary || "No work has been recorded for this step yet."}
        </div>
        {summaryOverflows ? (
          <button
            type="button"
            className="nodrag nopan nokey mt-1 inline-flex items-center gap-1 text-[10px] font-medium text-cyan-300 hover:text-cyan-200"
            aria-expanded={summaryExpanded}
            onPointerDown={(event) => event.stopPropagation()}
            onClick={(event) => {
              event.stopPropagation();
              setSummaryExpanded((open) => !open);
            }}
          >
            {summaryExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
            {summaryExpanded ? "Show less" : "Show more"}
          </button>
        ) : null}
        {step.branchName || step.markdownPath ? (
          <div className="mt-2 flex min-w-0 gap-1">
            {step.branchName ? (
              <span className="min-w-0 max-w-full truncate rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300" title={step.branchName}>
                {step.branchName}
              </span>
            ) : null}
            {step.markdownPath ? (
              <span className="min-w-0 max-w-full truncate rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300" title={step.markdownPath}>
                {step.markdownPath}
              </span>
            ) : null}
          </div>
        ) : null}
        {step.files.length ? (
          <div className="mt-2 flex flex-wrap gap-1">
            {step.files.slice(0, 2).map((file) => (
              <span
                key={file}
                className="max-w-full truncate rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300"
                title={file}
              >
                {file}
              </span>
            ))}
            {step.files.length > 2 ? (
              <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-400">
                +{step.files.length - 2}
              </span>
            ) : null}
          </div>
        ) : null}
      </div>
      <Handle
        type="source"
        position={Position.Right}
        className={`!h-3 !w-3 !border-2 !border-slate-950 ${phase.handle}`}
      />
    </div>
  );
});

WorkflowStepNodeView.displayName = "WorkflowStepNodeView";

function phaseConfig(kind: string): {
  icon: LucideIcon;
  border: string;
  selectedBorder: string;
  ring: string;
  header: string;
  badge: string;
  handle: string;
} {
  if (kind === "review") {
    return style(SearchCheck, "amber");
  }
  if (kind === "review_fix") {
    return style(Wrench, "violet");
  }
  if (kind === "verification") {
    return style(CheckCircle2, "emerald");
  }
  if (kind === "commit") {
    return style(GitCommitHorizontal, "indigo");
  }
  if (kind === "push") {
    return style(GitPullRequestArrow, "sky");
  }
  if (kind === "merge") {
    return style(GitMerge, "lime");
  }
  if (kind === "branch") {
    return style(GitBranch, "cyan");
  }
  if (kind === "markdown") {
    return style(FileText, "sky");
  }
  if (kind === "preflight") {
    return style(ClipboardList, "slate");
  }
  return style(Code2, "cyan");
}

function stepKindLabel(kind: string): string {
  if (kind === "preflight") return "Preflight";
  if (kind === "markdown") return "Markdown";
  if (kind === "branch") return "Branch";
  if (kind === "implementation") return "Implementation";
  if (kind === "review") return "Review";
  if (kind === "review_fix") return "Review fix";
  if (kind === "verification") return "Verification";
  if (kind === "commit") return "Commit";
  if (kind === "push") return "Push";
  if (kind === "merge") return "Merge";
  return kind;
}

function style(icon: LucideIcon, tone: "amber" | "violet" | "emerald" | "indigo" | "sky" | "lime" | "cyan" | "slate") {
  const colors = {
    amber: ["border-amber-500/70", "border-amber-300", "ring-amber-300/35", "bg-amber-950/30", "bg-amber-500/15 text-amber-200", "!bg-amber-300"],
    violet: ["border-violet-500/70", "border-violet-300", "ring-violet-300/35", "bg-violet-950/30", "bg-violet-500/15 text-violet-200", "!bg-violet-300"],
    emerald: ["border-emerald-500/70", "border-emerald-300", "ring-emerald-300/35", "bg-emerald-950/30", "bg-emerald-500/15 text-emerald-200", "!bg-emerald-300"],
    indigo: ["border-indigo-500/70", "border-indigo-300", "ring-indigo-300/35", "bg-indigo-950/30", "bg-indigo-500/15 text-indigo-200", "!bg-indigo-300"],
    sky: ["border-sky-500/70", "border-sky-300", "ring-sky-300/35", "bg-sky-950/30", "bg-sky-500/15 text-sky-200", "!bg-sky-300"],
    lime: ["border-lime-500/70", "border-lime-300", "ring-lime-300/35", "bg-lime-950/30", "bg-lime-500/15 text-lime-200", "!bg-lime-300"],
    cyan: ["border-cyan-500/70", "border-cyan-300", "ring-cyan-300/35", "bg-cyan-950/30", "bg-cyan-500/15 text-cyan-200", "!bg-cyan-300"],
    slate: ["border-slate-600", "border-slate-300", "ring-slate-300/30", "bg-slate-800/55", "bg-slate-700/80 text-slate-200", "!bg-slate-300"],
  }[tone];
  return {
    icon,
    border: colors[0],
    selectedBorder: colors[1],
    ring: colors[2],
    header: colors[3],
    badge: colors[4],
    handle: colors[5],
  };
}

function statusIcon(status: MarkdownWorkflowStepStatus): LucideIcon {
  if (status === "completed") return CheckCircle2;
  if (status === "skipped") return SkipForward;
  if (status === "blocked") return XCircle;
  return CircleDashed;
}

function statusLabel(status: MarkdownWorkflowStepStatus): string {
  if (status === "completed") return "Completed";
  if (status === "skipped") return "Skipped";
  if (status === "blocked") return "Blocked";
  if (status === "pending") return "Pending";
  return "Unknown";
}

function statusClass(status: MarkdownWorkflowStepStatus): string {
  if (status === "completed") return "bg-emerald-500/15 text-emerald-200";
  if (status === "skipped") return "bg-slate-700/60 text-slate-300";
  if (status === "blocked") return "bg-rose-500/15 text-rose-200";
  if (status === "pending") return "bg-amber-500/15 text-amber-200";
  return "bg-slate-800 text-slate-400";
}
