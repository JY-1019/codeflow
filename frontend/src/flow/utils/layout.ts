import type { Edge, Node } from "@xyflow/react";

/**
 * Lightweight column layout. Files & changed-symbols go in a middle column,
 * affected nodes go to the right, context nodes go to the left.
 */
export function layoutColumns(nodes: Node[], _edges: Edge[]): Node[] {
  const left: Node[] = [];
  const center: Node[] = [];
  const right: Node[] = [];

  for (const n of nodes) {
    const kind = (n.data as { kind?: string })?.kind;
    if (kind === "context") left.push(n);
    else if (kind === "affected") right.push(n);
    else center.push(n);
  }

  const positioned: Node[] = [];
  const placeColumn = (column: Node[], x: number) => {
    column.forEach((node, idx) => {
      positioned.push({
        ...node,
        position: { x, y: idx * 130 },
      });
    });
  };

  placeColumn(left, 0);
  placeColumn(center, 380);
  placeColumn(right, 760);

  return positioned;
}
