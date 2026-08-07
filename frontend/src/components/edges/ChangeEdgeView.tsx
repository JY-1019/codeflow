import { memo } from "react";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import { Book } from "lucide-react";

/** Edge color by kind — mirrors original codeflow's DEPENDENCY_COLORS map. */
export const EDGE_COLOR: Record<string, string> = {
  modifies: "#38bdf8",
  calls: "#a855f7",
  imports: "#22c55e",
  referenced_by: "#f59e0b",
  contains: "#64748b",
  renamed_from: "#fb923c",
  default: "#64748b",
};

interface EdgeData {
  kind?: string;
  label?: string;
  hasBody?: boolean;
  onOpenDoc?: (edgeId: string) => void;
}

export const ChangeEdgeView = memo((props: EdgeProps) => {
  const {
    id,
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
    data,
    selected,
    style = {},
  } = props;
  const edgeData = (data || {}) as EdgeData;
  const kind = edgeData.kind ?? "default";
  const baseColor = EDGE_COLOR[kind] ?? EDGE_COLOR.default;

  const isReferenced = kind === "referenced_by";
  const isContains = kind === "contains";
  const isImport = kind === "imports";

  const stroke = selected ? "#60a5fa" : baseColor;
  const strokeWidth = selected ? 3 : 2;
  const dashed = isReferenced || isContains ? "5 5" : isImport ? "10 4" : undefined;
  const opacity = typeof style.opacity === "number" ? style.opacity : 1;

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
        path={edgePath}
        style={{
          stroke,
          strokeWidth,
          strokeDasharray: dashed,
          opacity,
        }}
        markerEnd={`url(#cfl-arrow-${kind})`}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: "all",
            zIndex: 1000,
          }}
          className="nodrag nopan"
        >
          <div
            onClick={(e) => {
              e.stopPropagation();
              edgeData.onOpenDoc?.(id);
            }}
            className={`flex items-center gap-0.5 rounded-lg border shadow-lg ${
              selected ? "border-sky-400" : ""
            }`}
            style={{
              borderColor: selected ? undefined : baseColor,
              backgroundColor: "#1e293b",
              opacity: opacity < 0.5 ? 0 : 1,
            }}
          >
            <div className="flex items-center gap-1 border-r border-slate-700/60 px-1.5 py-1">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ backgroundColor: baseColor }}
              />
              <span className="text-[10px] uppercase tracking-wider text-slate-200">
                {edgeData.label || kind}
              </span>
            </div>
            <button
              className={`rounded-r-lg p-1 transition-colors ${
                edgeData.hasBody
                  ? "bg-purple-600/25 text-purple-300"
                  : "text-slate-500 hover:bg-slate-700"
              }`}
              title={edgeData.hasBody ? "Edge description available" : "No edge description"}
              onClick={(e) => {
                e.stopPropagation();
                edgeData.onOpenDoc?.(id);
              }}
            >
              <Book className="h-3 w-3" />
            </button>
          </div>
        </div>
      </EdgeLabelRenderer>
    </>
  );
});

ChangeEdgeView.displayName = "ChangeEdgeView";

/**
 * SVG arrow markers — one per edge kind so the arrowhead matches the line color.
 * Drop <EdgeArrowDefs /> once inside the ReactFlow tree.
 */
export function EdgeArrowDefs() {
  return (
    <svg className="absolute h-0 w-0">
      <defs>
        {Object.entries(EDGE_COLOR).map(([kind, color]) => (
          <marker
            key={kind}
            id={`cfl-arrow-${kind}`}
            viewBox="0 0 10 10"
            refX="9"
            refY="5"
            markerUnits="strokeWidth"
            markerWidth="10"
            markerHeight="10"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
          </marker>
        ))}
      </defs>
    </svg>
  );
}
