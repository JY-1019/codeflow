import type { Node, XYPosition } from "@xyflow/react";

const PREFIX = "codeflow-light:nodePositions";

export type PositionMap = Record<string, XYPosition>;

export function applySavedPositions(nodes: Node[], scope: string): Node[] {
  const saved = readPositions(scope);
  if (Object.keys(saved).length === 0) return nodes;
  return nodes.map((node) => {
    const position = saved[node.id];
    if (!position) return node;
    return { ...node, position };
  });
}

export function saveNodePosition(scope: string, nodeId: string, position: XYPosition): void {
  const saved = readPositions(scope);
  saved[nodeId] = { x: position.x, y: position.y };
  writePositions(scope, saved);
}

export function savePositionSnapshot(scope: string, snapshot: PositionMap): void {
  const saved = readPositions(scope);
  writePositions(scope, { ...saved, ...snapshot });
}

export function snapshotNodePositions(
  nodes: Node[],
  shouldInclude: (node: Node) => boolean = () => true
): PositionMap {
  return Object.fromEntries(
    nodes
      .filter(shouldInclude)
      .map((node) => [node.id, { x: node.position.x, y: node.position.y }])
  );
}

export function applyPositionSnapshot(nodes: Node[], snapshot: PositionMap): Node[] {
  return nodes.map((node) => {
    const position = snapshot[node.id];
    if (!position) return node;
    return { ...node, position: { x: position.x, y: position.y } };
  });
}

export function positionsEqual(a: PositionMap, b: PositionMap): boolean {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const key of keys) {
    if (!a[key] || !b[key]) return false;
    if (a[key].x !== b[key].x || a[key].y !== b[key].y) return false;
  }
  return true;
}

function readPositions(scope: string): PositionMap {
  try {
    const raw = window.localStorage.getItem(storageKey(scope));
    if (!raw) return {};
    const parsed = JSON.parse(raw) as PositionMap;
    if (!parsed || typeof parsed !== "object") return {};
    return parsed;
  } catch {
    return {};
  }
}

function writePositions(scope: string, positions: PositionMap): void {
  try {
    window.localStorage.setItem(storageKey(scope), JSON.stringify(positions));
  } catch {
    // localStorage may be unavailable in hardened desktop environments.
  }
}

function storageKey(scope: string): string {
  return `${PREFIX}:${scope}`;
}
