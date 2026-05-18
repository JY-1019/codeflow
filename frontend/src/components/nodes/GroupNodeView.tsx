import { memo } from "react";
import { Handle, Position, type NodeProps } from "@xyflow/react";
import {
  Clock3,
  FileText,
  FlaskConical,
  Hammer,
  RotateCcw,
  SearchCheck,
  ClipboardList,
  type LucideIcon,
} from "lucide-react";
import type { ChangeGroupPhase, ChangeGroupSummary } from "@/types/changes";

export interface GroupNodeData {
  name: string;
  createdAt: string;
  prompt: string;
  phase: ChangeGroupPhase;
  phaseLabel: string;
  sequence: number;
  fileCount: number;
  edgeCount: number;
  summary?: ChangeGroupSummary;
}

export const GroupNodeView = memo(({ data, selected }: NodeProps) => {
  const group = data as unknown as GroupNodeData;
  const prompt = group.prompt.trim() || "사용자 질의가 기록되지 않았습니다.";
  const phase = phaseConfig(group.phase);
  const PhaseIcon = phase.icon;
  const mainSummary =
    group.summary?.implementation?.[0] ||
    group.summary?.review?.[0] ||
    prompt;

  return (
    <div
      className={`relative w-[310px] rounded-md border bg-slate-900 shadow-lg transition-all ${
        selected ? `${phase.selectedBorder} ring-2 ${phase.ring}` : phase.border
      }`}
    >
      <Handle
        type="target"
        position={Position.Left}
        className={`!h-3 !w-3 !border-2 !border-slate-950 ${phase.handle}`}
      />
      <div className={`border-b border-slate-700/80 px-3 py-2 ${phase.header}`}>
        <div className="flex items-center justify-between gap-2">
          <div className={`inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${phase.badge}`}>
            <PhaseIcon className="h-3 w-3" />
            {group.phaseLabel || phase.label}
          </div>
          <div className="inline-flex items-center gap-1 text-[10px] text-slate-400">
            <Clock3 className="h-3 w-3" />
            {group.name}
          </div>
        </div>
        <div className="mt-2 line-clamp-2 text-[12px] leading-snug text-slate-100">
          {mainSummary}
        </div>
        <div className="mt-1 line-clamp-1 text-[11px] leading-snug text-slate-400">
          {prompt}
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 px-3 py-2 text-[11px] text-slate-300">
        <div className="flex items-center gap-1.5">
          <FileText className="h-3.5 w-3.5 text-sky-300" />
          {group.fileCount}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-emerald-300">+{group.summary?.added_lines ?? 0}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-rose-300">-{group.summary?.removed_lines ?? 0}</span>
        </div>
      </div>
      {group.summary?.technical_considerations?.length ? (
        <div className="flex min-h-8 flex-wrap gap-1 border-t border-slate-800 px-3 py-2">
          {group.summary.technical_considerations.slice(0, 2).map((item) => (
            <span
              key={item.label}
              className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300"
            >
              {item.label}
            </span>
          ))}
        </div>
      ) : (
        <div className="min-h-8 border-t border-slate-800 px-3 py-2 text-[10px] text-slate-500">
          세션 요약 대기
        </div>
      )}
      <Handle
        type="source"
        position={Position.Right}
        className={`!h-3 !w-3 !border-2 !border-slate-950 ${phase.handle}`}
      />
    </div>
  );
});

GroupNodeView.displayName = "GroupNodeView";

function phaseConfig(phase: ChangeGroupPhase | undefined): {
  label: string;
  icon: LucideIcon;
  border: string;
  selectedBorder: string;
  ring: string;
  header: string;
  badge: string;
  handle: string;
} {
  if (phase === "review") {
    return {
      label: "리뷰",
      icon: SearchCheck,
      border: "border-amber-500/70",
      selectedBorder: "border-amber-300",
      ring: "ring-amber-300/35",
      header: "bg-amber-950/30",
      badge: "bg-amber-500/15 text-amber-200",
      handle: "!bg-amber-300",
    };
  }
  if (phase === "review_fix") {
    return {
      label: "리뷰 반영",
      icon: RotateCcw,
      border: "border-violet-500/70",
      selectedBorder: "border-violet-300",
      ring: "ring-violet-300/35",
      header: "bg-violet-950/30",
      badge: "bg-violet-500/15 text-violet-200",
      handle: "!bg-violet-300",
    };
  }
  if (phase === "verification") {
    return {
      label: "검증",
      icon: FlaskConical,
      border: "border-emerald-500/70",
      selectedBorder: "border-emerald-300",
      ring: "ring-emerald-300/35",
      header: "bg-emerald-950/30",
      badge: "bg-emerald-500/15 text-emerald-200",
      handle: "!bg-emerald-300",
    };
  }
  if (phase === "planning") {
    return {
      label: "정리",
      icon: ClipboardList,
      border: "border-sky-500/70",
      selectedBorder: "border-sky-300",
      ring: "ring-sky-300/35",
      header: "bg-sky-950/30",
      badge: "bg-sky-500/15 text-sky-200",
      handle: "!bg-sky-300",
    };
  }
  return {
    label: "구현",
    icon: Hammer,
    border: "border-cyan-500/70",
    selectedBorder: "border-cyan-300",
    ring: "ring-cyan-300/35",
    header: "bg-cyan-950/30",
    badge: "bg-cyan-500/15 text-cyan-200",
    handle: "!bg-cyan-300",
  };
}
