import { BaseEdge, EdgeLabelRenderer, getBezierPath, type EdgeProps } from "@xyflow/react";

const EDGE_COLOR: Record<string, string> = {
  modifies: "#38bdf8",
  calls: "#a855f7",
  referenced_by: "#f59e0b",
  contains: "#64748b",
  renamed_from: "#f97316",
};

export function ChangeEdgeView(props: EdgeProps) {
  const { id, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, data, selected, markerEnd } = props;
  const kind = (data as { kind?: string })?.kind ?? "calls";
  const color = EDGE_COLOR[kind] ?? "#64748b";

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        markerEnd={markerEnd}
        style={{
          stroke: color,
          strokeWidth: selected ? 2.5 : 1.5,
          opacity: selected ? 1 : 0.85,
        }}
      />
      {(data as { label?: string })?.label ? (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: "all",
            }}
            className="rounded bg-slate-800/90 px-1.5 py-0.5 text-[10px] text-slate-200 border border-slate-700"
          >
            {(data as { label: string }).label}
          </div>
        </EdgeLabelRenderer>
      ) : null}
    </>
  );
}
