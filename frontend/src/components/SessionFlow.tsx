import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  Position,
  useReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from "@xyflow/react";
import { GitBranch } from "lucide-react";
import { GroupFrameNodeView } from "@/components/nodes/GroupFrameNodeView";
import { MarkdownCommandNodeView } from "@/components/nodes/MarkdownCommandNodeView";
import { WorkflowStepNodeView } from "@/components/nodes/WorkflowStepNodeView";
import { usePositionUndoRedo } from "@/flow/hooks/usePositionUndoRedo";
import { applySavedPositions } from "@/flow/utils/positions";
import type {
  ChangeGroup,
  ChangeGroupPhase,
  ChangeSessionResponse,
  MarkdownWorkflowRun,
  MarkdownWorkflowStep,
} from "@/types/changes";

const nodeTypes = {
  frame: GroupFrameNodeView,
  markdownCommand: MarkdownCommandNodeView,
  workflowStep: WorkflowStepNodeView,
};

interface SessionFlowProps {
  session: ChangeSessionResponse | null;
  activeGroupId: string | null;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  selectedGroupId: string | null;
  focusTarget?: SessionGroupFocusTarget | null;
  onSelectGroup: (id: string | null) => void;
  onSelectNode: (groupId: string, nodeId: string | null) => void;
  onSelectEdge: (groupId: string, edgeId: string | null) => void;
}

export interface SessionGroupFocusTarget {
  groupId: string;
  nonce: number;
}

const GROUP_GAP_X = 140;
const STEP_GAP_X = 360;
const STEP_GAP_Y = 148;
const RUN_GAP_Y = 640;
const BASE_Y = 118;
const NODE_WIDTH = 228;
const FLOW_COLUMN_COUNT = 5;
const FRAME_PADDING_X = 34;
const FRAME_TOP_Y = 42;
const FRAME_BOTTOM_PADDING = 94;
const FLOW_STEP_KINDS = new Set([
  "preflight",
  "markdown",
  "branch",
  "implementation",
  "review",
  "review_fix",
  "verification",
  "commit",
  "push",
  "merge",
]);
const TERMINAL_STEP_KINDS = new Set(["verification", "commit", "push", "merge"]);

function buildSessionFlow(session: ChangeSessionResponse): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = [];
  const edges: Edge[] = [];
  let previousGroupLastNode: string | null = null;
  let groupX = 0;

  session.groups.forEach((group, index) => {
    const rows = visualStepRowsForGroup(group);
    const rowSpan = Math.max(
      RUN_GAP_Y,
      maxGridRows(rows) * STEP_GAP_Y + FRAME_BOTTOM_PADDING
    );
    const frameWidth = Math.max(
      380,
      FRAME_PADDING_X * 2 + NODE_WIDTH + (FLOW_COLUMN_COUNT - 1) * STEP_GAP_X
    );
    const frameHeight = BASE_Y + rows.length * rowSpan + FRAME_BOTTOM_PADDING;
    const frameId = `frame::${group.id}`;

    nodes.push({
      id: frameId,
      type: "frame",
      position: { x: groupX - FRAME_PADDING_X, y: FRAME_TOP_Y },
      data: {
        width: frameWidth,
        height: frameHeight,
        name: `group ${group.sequence ?? index + 1} · ${group.name}`,
      },
      draggable: false,
      selectable: false,
      zIndex: 0,
    });

    let groupFirstNode: string | null = null;
    let groupLastNode: string | null = null;
    rows.forEach((row, rowIndex) => {
      let previousStepNode: string | null = null;
      const stepPositions = stepGridPositions(row.steps);
      row.steps.forEach((step, stepIndex) => {
        const stepNodeId = `step::${group.id}::${row.id}::${stepIndex}::${step.id}`;
        const stepPosition = stepPositions[stepIndex];
        nodes.push({
          id: stepNodeId,
          type: step.kind === "markdown" ? "markdownCommand" : "workflowStep",
          position: {
            x: groupX + FRAME_PADDING_X + stepPosition.column * STEP_GAP_X,
            y: BASE_Y + rowIndex * rowSpan + stepPosition.row * STEP_GAP_Y,
          },
          sourcePosition: Position.Right,
          targetPosition: Position.Left,
          data: {
            ...step,
            ...(step.kind === "markdown" ? row.run : {}),
            groupId: group.id,
            groupName: group.name,
            runId: row.id,
            runTitle: row.title,
          },
          draggable: true,
          zIndex: 2,
        });

        if (previousStepNode) {
          edges.push(workflowEdge(`edge::${previousStepNode}->${stepNodeId}`, previousStepNode, stepNodeId, step.kind));
        }
        previousStepNode = stepNodeId;
        groupFirstNode = groupFirstNode ?? stepNodeId;
        groupLastNode = stepNodeId;
      });
    });

    if (previousGroupLastNode && groupFirstNode) {
      edges.push(workflowEdge(`timeline::${previousGroupLastNode}->${groupFirstNode}`, previousGroupLastNode, groupFirstNode, "timeline"));
    }

    previousGroupLastNode = groupLastNode ?? previousGroupLastNode;
    groupX += frameWidth + GROUP_GAP_X;
  });

  return { nodes, edges };
}

function maxGridRows(rows: VisualStepRow[]): number {
  let maxRow = 0;
  rows.forEach((row) => {
    stepGridPositions(row.steps).forEach((position) => {
      maxRow = Math.max(maxRow, position.row);
    });
  });
  return maxRow + 1;
}

interface VisualStepRow {
  id: string;
  title: string;
  run: MarkdownWorkflowRun;
  steps: WorkflowStepDisplayData[];
}

interface WorkflowStepDisplayData extends MarkdownWorkflowStep {
  runTitle?: string;
  markdownPath?: string;
  branchName?: string;
  skillLabel?: string;
}

function visualStepRowsForGroup(group: ChangeGroup): VisualStepRow[] {
  const rows = (group.workflow_runs ?? [])
    .map((run, index) => {
      const title = run.markdown_title || run.markdown_path || run.command_label || `루프 ${index + 1}`;
      const steps = run.steps
        .filter((step) => FLOW_STEP_KINDS.has(step.kind))
        .map((step) => ({
          ...step,
          runTitle: title,
          markdownPath: run.markdown_path,
          branchName: run.branch_name,
          skillLabel: workflowSkillLabel(run.skill, run.skill_label),
        }));
      return { id: run.id, title, run, steps };
    })
    .filter((row) => row.steps.length > 0);

  if (rows.length > 0) {
    return rows;
  }

  const phase = group.phase ?? "implementation";
  const kind = phase === "review" || phase === "review_fix" || phase === "verification"
    ? phase
    : "implementation";
  return [{
    id: group.id,
    steps: [
      {
        id: group.id,
        kind,
        label: group.phase_label ?? phaseLabel(phase),
        summary: fallbackStepSummary(group, kind),
        detail: "",
        status: "completed",
        files: group.summary?.changed_files ?? [],
        runTitle: group.name,
        skillLabel: "캡처된 턴",
      },
    ],
    title: group.name,
    run: {
      id: group.id,
      skill: "captured-turn",
      skill_label: "캡처된 턴",
      command_label: group.name,
      markdown_path: "",
      markdown_title: group.name,
      markdown_content: group.user_prompt,
      branch_name: "",
      status: "completed",
      steps: [],
    },
  }];
}

function fallbackStepSummary(group: ChangeGroup, kind: string): string {
  if (kind === "review" || kind === "review_fix" || kind === "verification") {
    return (
      group.summary?.review?.[0] ||
      group.summary?.implementation?.[0] ||
      "이 그룹의 리뷰나 검증 내용이 아직 없습니다."
    );
  }
  return (
    group.summary?.implementation?.[0] ||
    group.summary?.review?.[0] ||
    "이 그룹의 구현이나 리뷰 내용이 아직 없습니다."
  );
}

function workflowEdge(id: string, source: string, target: string, kind: string): Edge {
  return {
    id,
    source,
    target,
    type: "smoothstep",
    animated: kind === "review_fix",
    style: {
      stroke: workflowColor(kind),
      strokeDasharray: kind === "review" || kind === "timeline" ? "5 7" : undefined,
      strokeWidth: kind === "timeline" ? 1.5 : 2,
    },
  };
}

function stepGridPositions(steps: MarkdownWorkflowStep[]): Array<{ column: number; row: number }> {
  const duplicateCounts = new Map<string, number>();
  let reviewCount = 0;
  let currentLoopIndex = 0;

  return steps.map((step, stepIndex) => {
    const duplicateIndex = duplicateCounts.get(step.kind) ?? 0;
    duplicateCounts.set(step.kind, duplicateIndex + 1);

    let loopIndex = duplicateIndex;
    if (step.kind === "review") {
      loopIndex = reviewCount;
      currentLoopIndex = loopIndex;
      reviewCount += 1;
    } else if (step.kind === "review_fix") {
      loopIndex = reviewCount > 0 ? Math.max(reviewCount - 1, duplicateIndex) : duplicateIndex;
      currentLoopIndex = loopIndex;
    } else if (TERMINAL_STEP_KINDS.has(step.kind)) {
      loopIndex = currentLoopIndex;
    } else if (step.kind === "implementation") {
      currentLoopIndex = Math.max(currentLoopIndex, duplicateIndex);
    }

    return stepGridPosition(step, stepIndex, loopIndex);
  });
}

function stepGridPosition(
  step: MarkdownWorkflowStep,
  fallbackIndex: number,
  loopIndex = 0
): { column: number; row: number } {
  const rowOffset = loopIndex * 2;
  if (step.kind === "preflight") return { column: 0, row: 0 };
  if (step.kind === "markdown") return { column: 0, row: 1 };
  if (step.kind === "branch") return { column: 0, row: 2 };
  if (step.kind === "implementation") return { column: 1, row: 1 + rowOffset };
  if (step.kind === "review") return { column: 2, row: 0 + rowOffset };
  if (step.kind === "review_fix") return { column: 3, row: 1 + rowOffset };
  if (step.kind === "verification") return { column: 4, row: 0 + rowOffset };
  if (step.kind === "commit") return { column: 4, row: 1 + rowOffset };
  if (step.kind === "push") return { column: 4, row: 2 + rowOffset };
  if (step.kind === "merge") return { column: 4, row: 3 + rowOffset };
  return { column: Math.min(FLOW_COLUMN_COUNT - 1, fallbackIndex), row: 1 + rowOffset };
}

function SessionFlowInner({
  session,
  selectedNodeId,
  selectedGroupId,
  focusTarget,
  onSelectGroup,
  onSelectNode,
}: SessionFlowProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);
  const nodesRef = useRef<Node[]>([]);
  const { fitView, setCenter } = useReactFlow();
  const positionScope = session
    ? `session-review-units:v2:${session.session_id ?? session.project_root}`
    : "session-review-units";

  useEffect(() => {
    if (!session) {
      setNodes([]);
      setEdges([]);
      return;
    }
    const flow = buildSessionFlow(session);
    setNodes(applySavedPositions(flow.nodes, positionScope));
    setEdges(flow.edges);
  }, [session, positionScope, setNodes, setEdges]);

  const isPositionTracked = useCallback(
    (node: Node) => node.type === "workflowStep" || node.type === "markdownCommand",
    []
  );
  const { handleNodeDragStart, handleNodeDragStop } = usePositionUndoRedo({
    nodes,
    setNodes,
    positionScope,
    isTracked: isPositionTracked,
  });

  useEffect(() => {
    nodesRef.current = nodes;
  }, [nodes]);

  const decoratedNodes = useMemo(
    () =>
      nodes.map((node) => ({
        ...node,
        selected: selectedNodeId
          ? node.id === selectedNodeId
          : Boolean(selectedGroupId && (node.data as { groupId?: string }).groupId === selectedGroupId),
      })),
    [nodes, selectedGroupId, selectedNodeId]
  );

  useEffect(() => {
    if (!focusTarget) return;

    const timer = window.setTimeout(() => {
      const groupNodes = nodesRef.current
        .filter((node) => (node.data as { groupId?: string }).groupId === focusTarget.groupId)
      const groupNodeRefs = groupNodes.map((node) => ({ id: node.id }));
      if (groupNodes.length === 0) return;

      if (groupNodes.length > 6) {
        const minX = Math.min(...groupNodes.map((node) => node.position.x));
        const minY = Math.min(...groupNodes.map((node) => node.position.y));
        void setCenter(minX + 420, minY + 230, {
          zoom: 0.58,
          duration: 650,
        });
        return;
      }

      void fitView({
        nodes: groupNodeRefs,
        padding: 0.24,
        duration: 650,
      });
    }, 80);

    return () => window.clearTimeout(timer);
  }, [fitView, focusTarget?.nonce, setCenter]);

  if (!session || session.groups.length === 0) {
    return <EmptySession />;
  }

  return (
    <div className="relative h-full w-full">
      <ReactFlow
        nodes={decoratedNodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeDragStart={handleNodeDragStart}
        onNodeDragStop={handleNodeDragStop}
        onNodeClick={(_, node) => {
          const id = (node.data as { groupId?: string }).groupId;
          if ((node.type === "workflowStep" || node.type === "markdownCommand") && id) {
            onSelectNode(id, node.id);
            return;
          }
          if (id) onSelectGroup(id);
        }}
        onPaneClick={() => onSelectGroup(null)}
        defaultViewport={{ x: 24, y: 32, zoom: 0.64 }}
        proOptions={{ hideAttribution: true }}
        minZoom={0.15}
        maxZoom={2.4}
        panOnDrag
        zoomOnScroll
        zoomOnPinch
      >
        <Background gap={22} color="#1e293b" />
        <Controls position="bottom-right" showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(node) => miniMapNodeColor(node)}
          maskColor="rgba(2, 6, 23, 0.72)"
        />
      </ReactFlow>
      <div className="absolute bottom-3 left-3 z-10 rounded-md border border-slate-700/70 bg-slate-900/85 px-2 py-1.5 text-[10px] shadow-lg backdrop-blur">
        <div className="mb-1 uppercase tracking-wider text-slate-500">흐름 단위</div>
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          <LegendDot color="#38bdf8" label="명령/브랜치" />
          <LegendDot color="#22d3ee" label="구현" />
          <LegendDot color="#f59e0b" label="리뷰" />
          <LegendDot color="#8b5cf6" label="리뷰 반영" />
          <LegendDot color="#22c55e" label="검증" />
          <LegendDot color="#6366f1" label="커밋" />
          <LegendDot color="#84cc16" label="푸시/병합" />
        </div>
      </div>
    </div>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: color }} />
      <span className="text-slate-300">{label}</span>
    </div>
  );
}

function EmptySession() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-400">
      <GitBranch className="h-8 w-8 text-slate-600" />
      <div className="text-[13px]">아직 기록된 flow가 없습니다.</div>
      <div className="max-w-md text-[12px] text-slate-500">
        Codex 또는 Claude skill이 워크플로우 이벤트를 보내면 구현/리뷰 단위가 자동으로 채워집니다.
      </div>
    </div>
  );
}

function workflowSkillLabel(skill: string, label?: string): string {
  const cleaned = label?.trim() || skill.trim();
  const known: Record<string, string> = {
    "markdown-branch-push": "Markdown 브랜치 푸시",
    "markdown-branch-commit": "Markdown 브랜치 커밋",
    "captured-turn": "캡처된 턴",
    "Markdown Branch Push": "Markdown 브랜치 푸시",
    "Markdown Branch Commit": "Markdown 브랜치 커밋",
    "Captured turn": "캡처된 턴",
  };
  return known[cleaned] ?? known[skill] ?? cleaned;
}

function phaseLabel(phase: ChangeGroupPhase): string {
  if (phase === "review") return "리뷰";
  if (phase === "review_fix") return "리뷰 반영";
  if (phase === "verification") return "검증";
  if (phase === "planning") return "정리";
  return "구현";
}

function phaseNodeColor(phase: ChangeGroupPhase | undefined): string {
  if (phase === "review") return "#f59e0b";
  if (phase === "review_fix") return "#8b5cf6";
  if (phase === "verification") return "#22c55e";
  if (phase === "planning") return "#38bdf8";
  return "#22d3ee";
}

function workflowColor(kind: string): string {
  if (kind === "preflight" || kind === "markdown" || kind === "branch") return "#38bdf8";
  if (kind === "review") return "#f59e0b";
  if (kind === "review_fix") return "#8b5cf6";
  if (kind === "verification") return "#22c55e";
  if (kind === "commit") return "#6366f1";
  if (kind === "push") return "#0ea5e9";
  if (kind === "merge") return "#84cc16";
  if (kind === "timeline") return "#64748b";
  return "#22d3ee";
}

function miniMapNodeColor(node: Node): string {
  if (node.type === "frame") return "#0f172a";
  if (node.type === "workflowStep" || node.type === "markdownCommand") {
    return workflowColor(String((node.data as { kind?: string }).kind ?? ""));
  }
  return phaseNodeColor((node.data as { phase?: ChangeGroupPhase }).phase);
}

export function SessionFlow(props: SessionFlowProps) {
  return (
    <ReactFlowProvider>
      <SessionFlowInner {...props} />
    </ReactFlowProvider>
  );
}
