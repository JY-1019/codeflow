import { memo } from "react";
import type { NodeProps } from "@xyflow/react";

export interface GroupFrameData {
  width: number;
  height: number;
  name: string;
}

export const GroupFrameNodeView = memo(({ data, selected }: NodeProps) => {
  const frame = data as unknown as GroupFrameData;
  return (
    <div
      className={`cursor-move rounded-md border-2 border-dashed bg-slate-900/10 ${
        selected ? "border-cyan-300/80" : "border-cyan-500/40"
      }`}
      style={{
        width: frame.width,
        height: frame.height,
        boxShadow: selected ? "0 0 0 1px rgba(103, 232, 249, 0.35)" : undefined,
      }}
    >
      <div className="absolute left-3 top-[-10px] bg-slate-950 px-2 text-[10px] uppercase tracking-widest text-cyan-300/80">
        {frame.name}
      </div>
    </div>
  );
});

GroupFrameNodeView.displayName = "GroupFrameNodeView";
