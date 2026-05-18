import { Position, type Edge, type Node } from "@xyflow/react";

const COLUMN_GAP = 500;
const ROW_GAP = 205;
const ISOLATED_SECTION_GAP = 150;
const MIN_ISOLATED_COLUMNS = 3;

/**
 * Dependency-aware horizontal layout.
 *
 * Most edges are rendered left-to-right from the file that uses/imports
 * something to the file it depends on. `referenced_by` is a reverse semantic
 * edge, so we flip it only for layout to keep changed files visually first.
 */
export function layoutColumns(nodes: Node[], edges: Edge[]): Node[] {
  if (nodes.length === 0) return nodes;

  const ids = new Set(nodes.map((node) => node.id));
  const orderedEdges = edges
    .map((edge) => layoutDirection(edge))
    .filter(([source, target]) => ids.has(source) && ids.has(target) && source !== target);

  const connectedIds = new Set(orderedEdges.flat());
  if (connectedIds.size === 0) {
    return layoutIsolated(nodes, 0, MIN_ISOLATED_COLUMNS);
  }

  const connectedNodes = nodes.filter((node) => connectedIds.has(node.id));
  const isolatedNodes = nodes.filter((node) => !connectedIds.has(node.id));
  const connectedLayout = layoutConnected(connectedNodes, orderedEdges);

  if (isolatedNodes.length === 0) {
    return connectedLayout;
  }

  const maxConnectedY = Math.max(...connectedLayout.map((node) => node.position.y), 0);
  const connectedColumns =
    Math.max(...connectedLayout.map((node) => Math.round(node.position.x / COLUMN_GAP)), 0) + 1;
  const isolatedLayout = layoutIsolated(
    isolatedNodes,
    maxConnectedY + ROW_GAP + ISOLATED_SECTION_GAP,
    Math.max(MIN_ISOLATED_COLUMNS, connectedColumns)
  );

  return [...connectedLayout, ...isolatedLayout];
}

function layoutConnected(nodes: Node[], orderedEdges: [string, string][]): Node[] {
  const depthById = new Map<string, number>();

  for (const node of nodes) {
    const kind = (node.data as { kind?: string })?.kind;
    depthById.set(node.id, kind === "changed" ? 0 : 1);
  }

  for (let pass = 0; pass < nodes.length; pass += 1) {
    let changed = false;
    for (const [source, target] of orderedEdges) {
      const sourceDepth = depthById.get(source) ?? 0;
      const nextDepth = Math.min(sourceDepth + 1, 8);
      if ((depthById.get(target) ?? 0) < nextDepth) {
        depthById.set(target, nextDepth);
        changed = true;
      }
    }
    if (!changed) break;
  }

  const columns = new Map<number, Node[]>();
  for (const node of nodes) {
    const depth = depthById.get(node.id) ?? 0;
    const column = columns.get(depth) ?? [];
    column.push(node);
    columns.set(depth, column);
  }

  const laidOut: Node[] = [];
  for (const depth of Array.from(columns.keys()).sort((a, b) => a - b)) {
    const column = [...(columns.get(depth) ?? [])].sort(compareNodes);
    column.forEach((node, index) => {
      laidOut.push({
        ...node,
        position: { x: depth * COLUMN_GAP, y: index * ROW_GAP },
        sourcePosition: Position.Right,
        targetPosition: Position.Left,
      });
    });
  }

  return laidOut;
}

function layoutIsolated(nodes: Node[], yOffset: number, columns: number): Node[] {
  return [...nodes].sort(compareNodes).map((node, index) => ({
    ...node,
    position: {
      x: (index % columns) * COLUMN_GAP,
      y: yOffset + Math.floor(index / columns) * ROW_GAP,
    },
    sourcePosition: Position.Right,
    targetPosition: Position.Left,
  }));
}

function layoutDirection(edge: Edge): [string, string] {
  const kind = (edge.data as { kind?: string } | undefined)?.kind;
  if (kind === "referenced_by") return [edge.target, edge.source];
  return [edge.source, edge.target];
}

function compareNodes(a: Node, b: Node): number {
  const dataA = a.data as { kind?: string; status?: string; file?: string; label?: string };
  const dataB = b.data as { kind?: string; status?: string; file?: string; label?: string };
  return (
    kindRank(dataA.kind) - kindRank(dataB.kind) ||
    statusRank(dataA.status) - statusRank(dataB.status) ||
    String(dataA.file ?? dataA.label ?? a.id).localeCompare(
      String(dataB.file ?? dataB.label ?? b.id)
    )
  );
}

function kindRank(kind?: string): number {
  if (kind === "changed") return 0;
  if (kind === "affected") return 1;
  if (kind === "context") return 2;
  return 3;
}

function statusRank(status?: string): number {
  if (status === "modified") return 0;
  if (status === "added") return 1;
  if (status === "renamed") return 2;
  if (status === "deleted") return 3;
  return 4;
}
