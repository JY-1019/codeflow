import { useEffect, useMemo } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from "@xyflow/react";
import { ChangeNodeView } from "./nodes/ChangeNodeView";
import { ChangeEdgeView } from "./edges/ChangeEdgeView";
import { layoutColumns } from "@/flow/utils/layout";
import type { ChangeEdge, ChangeGraphResponse, ChangeNode } from "@/types/changes";

const nodeTypes = { change: ChangeNodeView };
const edgeTypes = { change: ChangeEdgeView };

interface ChangeFlowProps {
  graph: ChangeGraphResponse | null;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onSelectNode: (id: string | null) => void;
  onSelectEdge: (id: string | null) => void;
}

function buildFlowNodes(graphNodes: ChangeNode[]): Node[] {
  return graphNodes.map((n) => ({
    id: n.id,
    type: "change",
    position: { x: 0, y: 0 },
    data: { ...n },
  }));
}

function buildFlowEdges(graphEdges: ChangeEdge[]): Edge[] {
  return graphEdges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    type: "change",
    data: { kind: e.kind, label: e.label },
  }));
}

function ChangeFlowInner({
  graph,
  selectedNodeId,
  selectedEdgeId,
  onSelectNode,
  onSelectEdge,
}: ChangeFlowProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    if (!graph) {
      setNodes([]);
      setEdges([]);
      return;
    }
    const laidOut = layoutColumns(buildFlowNodes(graph.nodes), buildFlowEdges(graph.edges));
    setNodes(laidOut);
    setEdges(buildFlowEdges(graph.edges));
  }, [graph, setNodes, setEdges]);

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
      })),
    [edges, selectedEdgeId]
  );

  return (
    <ReactFlow
      nodes={decoratedNodes}
      edges={decoratedEdges}
      nodeTypes={nodeTypes}
      edgeTypes={edgeTypes}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
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
    >
      <Background gap={20} color="#1e293b" />
      <Controls className="!bg-slate-800 !text-slate-200" />
      <MiniMap
        pannable
        zoomable
        nodeColor={(n) => {
          const status = (n.data as { status?: string })?.status;
          if (status === "added") return "#22c55e";
          if (status === "deleted") return "#ef4444";
          if (status === "renamed") return "#f59e0b";
          if (status === "modified") return "#3b82f6";
          return "#64748b";
        }}
        maskColor="rgba(2, 6, 23, 0.7)"
      />
    </ReactFlow>
  );
}

export function ChangeFlow(props: ChangeFlowProps) {
  return (
    <ReactFlowProvider>
      <ChangeFlowInner {...props} />
    </ReactFlowProvider>
  );
}
