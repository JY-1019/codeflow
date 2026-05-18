import { useCallback, useEffect, useMemo } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from "@xyflow/react";
import { ChangeNodeView } from "./nodes/ChangeNodeView";
import { ChangeEdgeView, EdgeArrowDefs, EDGE_COLOR } from "./edges/ChangeEdgeView";
import { usePositionUndoRedo } from "@/flow/hooks/usePositionUndoRedo";
import { layoutColumns } from "@/flow/utils/layout";
import { applySavedPositions } from "@/flow/utils/positions";
import type { ChangeEdge, ChangeGraphResponse, ChangeNode } from "@/types/changes";

const nodeTypes = { change: ChangeNodeView };
const edgeTypes = { change: ChangeEdgeView };

interface ChangeFlowProps {
  graph: ChangeGraphResponse | null;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  focusTarget?: FlowFocusTarget | null;
  onSelectNode: (id: string | null) => void;
  onSelectEdge: (id: string | null) => void;
}

export interface FlowFocusTarget {
  kind: "node" | "edge";
  id: string;
  nonce: number;
}

function buildFlowNodes(graphNodes: ChangeNode[]): Node[] {
  return graphNodes.map((n) => ({
    id: n.id,
    type: "change",
    position: { x: 0, y: 0 },
    data: { ...n, hasBody: Boolean(n.body && n.body.trim()) },
  }));
}

function buildFlowEdges(graphEdges: ChangeEdge[]): Edge[] {
  return graphEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: "change",
    data: {
      kind: e.kind,
      label: e.label,
      hasBody: Boolean(e.body && e.body.trim()),
    },
  }));
}

function ChangeFlowInner({
  graph,
  selectedNodeId,
  selectedEdgeId,
  focusTarget,
  onSelectNode,
  onSelectEdge,
}: ChangeFlowProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const { fitView } = useReactFlow();
  const positionScope = graph
    ? `review:${graph.project_root}:${graph.source}:${graph.base_ref ?? ""}:${graph.head_ref ?? ""}`
    : "review";

  useEffect(() => {
    if (!graph) {
      setNodes([]);
      setEdges([]);
      return;
    }
    const flowEdges = buildFlowEdges(graph.edges);
    const laidOut = applySavedPositions(
      layoutColumns(buildFlowNodes(graph.nodes), flowEdges),
      positionScope
    );
    setNodes(laidOut);
    setEdges(flowEdges);
  }, [graph, positionScope, setNodes, setEdges]);

  const isPositionTracked = useCallback((node: Node) => node.type === "change", []);
  const { handleNodeDragStart, handleNodeDragStop } = usePositionUndoRedo({
    nodes,
    setNodes,
    positionScope,
    isTracked: isPositionTracked,
  });

  const decoratedNodes = useMemo(
    () =>
      nodes.map((n) => ({
        ...n,
        selected: n.id === selectedNodeId,
      })),
    [nodes, selectedNodeId]
  );

  const decoratedEdges = useMemo(
    () =>
      edges.map((e) => ({
        ...e,
        selected: e.id === selectedEdgeId,
        data: {
          ...e.data,
          onOpenDoc: (edgeId: string) => {
            onSelectEdge(edgeId);
            onSelectNode(null);
          },
        },
      })),
    [edges, onSelectEdge, onSelectNode, selectedEdgeId]
  );

  useEffect(() => {
    if (!focusTarget || nodes.length === 0) return;

    const timer = window.setTimeout(() => {
      if (focusTarget.kind === "node") {
        if (!nodes.some((node) => node.id === focusTarget.id)) return;
        void fitView({
          nodes: [{ id: focusTarget.id }],
          padding: 0.55,
          duration: 650,
        });
        return;
      }

      const edge = edges.find((item) => item.id === focusTarget.id);
      if (!edge) return;
      void fitView({
        nodes: [{ id: edge.source }, { id: edge.target }],
        padding: 0.35,
        duration: 650,
      });
    }, 80);

    return () => window.clearTimeout(timer);
  }, [fitView, focusTarget?.nonce]);

  return (
    <div className="relative h-full w-full">
      <EdgeArrowDefs />
      <ReactFlow
        nodes={decoratedNodes}
        edges={decoratedEdges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStart={handleNodeDragStart}
        onNodeDragStop={handleNodeDragStop}
        onNodeClick={(_, node) => {
          onSelectNode(node.id);
          onSelectEdge(null);
        }}
        onEdgeClick={(_, edge) => {
          onSelectEdge(edge.id);
          onSelectNode(null);
        }}
        onPaneClick={() => {
          onSelectNode(null);
          onSelectEdge(null);
        }}
        fitView
        fitViewOptions={{ padding: 0.25 }}
        proOptions={{ hideAttribution: true }}
        zoomOnScroll
        zoomOnPinch
        zoomOnDoubleClick
        panOnDrag
        panOnScroll={false}
        minZoom={0.1}
        maxZoom={2.5}
      >
        <Background gap={20} color="#1e293b" />
        <Controls position="bottom-right" showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(n) => {
            const status = (n.data as { status?: string })?.status;
            if (status === "added") return "#4ade80";
            if (status === "deleted") return "#f87171";
            if (status === "renamed") return "#fb923c";
            if (status === "modified") return "#60a5fa";
            return "#64748b";
          }}
          maskColor="rgba(2, 6, 23, 0.7)"
        />
      </ReactFlow>
      <EdgeLegend />
    </div>
  );
}

function EdgeLegend() {
  const entries: { kind: string; label: string }[] = [
    { kind: "contains", label: "contains" },
    { kind: "calls", label: "calls" },
    { kind: "imports", label: "imports" },
    { kind: "referenced_by", label: "uses" },
    { kind: "renamed_from", label: "renamed" },
  ];
  return (
    <div className="absolute bottom-3 left-3 z-10 rounded-md border border-slate-700/70 bg-slate-900/85 px-2 py-1.5 text-[10px] shadow-lg backdrop-blur">
      <div className="mb-1 uppercase tracking-wider text-slate-500">edge legend</div>
      <div className="flex flex-wrap gap-x-3 gap-y-1">
        {entries.map((e) => (
          <div key={e.kind} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-full"
              style={{ backgroundColor: EDGE_COLOR[e.kind] ?? EDGE_COLOR.default }}
            />
            <span className="text-slate-300">{e.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ChangeFlow(props: ChangeFlowProps) {
  return (
    <ReactFlowProvider>
      <ChangeFlowInner {...props} />
    </ReactFlowProvider>
  );
}
