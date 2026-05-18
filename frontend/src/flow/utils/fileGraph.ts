import type { ChangeEdge, ChangeGraphResponse, ChangeNode } from "@/types/changes";

export interface FileGraph {
  nodes: ChangeNode[];
  edges: ChangeEdge[];
}

export function toFileGraph(graph: ChangeGraphResponse): FileGraph {
  const groupedNodes = new Map<string, ChangeNode[]>();

  for (const node of graph.nodes) {
    if (!node.file) continue;
    const group = groupedNodes.get(node.file) ?? [];
    group.push(node);
    groupedNodes.set(node.file, group);
  }

  const nodesByFile = new Map<string, ChangeNode>();
  for (const [file, nodes] of groupedNodes.entries()) {
    nodesByFile.set(file, asAggregatedFileNode(nodes));
  }

  const nodeIdByFile = new Map(
    Array.from(nodesByFile.values()).map((node) => [node.file, node.id])
  );
  const rawNodeById = new Map(graph.nodes.map((node) => [node.id, node]));
  const edgeGroups = new Map<
    string,
    { source: ChangeNode; target: ChangeNode; edges: ChangeEdge[] }
  >();

  for (const edge of graph.edges) {
    const source = rawNodeById.get(edge.source);
    const target = rawNodeById.get(edge.target);
    if (!source || !target || source.file === target.file) continue;

    const sourceId = nodeIdByFile.get(source.file);
    const targetId = nodeIdByFile.get(target.file);
    if (!sourceId || !targetId) continue;

    const key = `${sourceId}->${targetId}:${edge.kind}`;
    const group = edgeGroups.get(key) ?? { source, target, edges: [] };
    group.edges.push(edge);
    edgeGroups.set(key, group);
  }

  const edgesByPair = new Map<string, ChangeEdge>();
  for (const [key, group] of edgeGroups.entries()) {
    const first = group.edges[0];
    const sourceId = nodeIdByFile.get(group.source.file);
    const targetId = nodeIdByFile.get(group.target.file);
    if (!first || !sourceId || !targetId) continue;

    edgesByPair.set(key, {
      ...first,
      id: `file-edge::${key}`,
      source: sourceId,
      target: targetId,
      summary: aggregateEdgeSummary(group.edges, group.source.file, group.target.file),
      body: aggregateEdgeBody(group.edges, group.source.file, group.target.file),
    });
  }

  return {
    nodes: Array.from(nodesByFile.values()),
    edges: Array.from(edgesByPair.values()),
  };
}

export function toFileGraphResponse(graph: ChangeGraphResponse): ChangeGraphResponse {
  const fileGraph = toFileGraph(graph);
  return {
    ...graph,
    nodes: fileGraph.nodes,
    edges: fileGraph.edges,
  };
}

function asAggregatedFileNode(nodes: ChangeNode[]): ChangeNode {
  const best = [...nodes].sort((a, b) => rankNode(b) - rankNode(a))[0];
  const fileNode = asFileNode(best);
  const fileLevel = nodes.find((node) => node.symbol_kind === "file");

  return {
    ...fileNode,
    added_lines: fileLevel?.added_lines ?? sum(nodes.map((node) => node.added_lines)),
    removed_lines: fileLevel?.removed_lines ?? sum(nodes.map((node) => node.removed_lines)),
    snippet: fileLevel?.snippet || firstNonEmpty(nodes.map((node) => node.snippet)),
    summary: aggregateNodeSummary(nodes, fileNode.summary),
    body: aggregateNodeBody(nodes),
  };
}

function asFileNode(node: ChangeNode): ChangeNode {
  if (node.symbol_kind === "file") return node;
  const safeFile = node.file.replace(/\//g, "__").replace(/\./g, "_");
  return {
    ...node,
    id: `file::${safeFile}`,
    label: node.file.split("/").pop() || node.file,
    symbol_kind: "file",
    start_line: null,
    end_line: null,
  };
}

function aggregateNodeSummary(nodes: ChangeNode[], fallback: string): string {
  return nodes.find((node) => node.symbol_kind === "file")?.summary || fallback;
}

function aggregateNodeBody(nodes: ChangeNode[]): string {
  const ordered = [...nodes].sort((a, b) => rankNode(b) - rankNode(a));
  const parts: string[] = [];

  for (const node of ordered) {
    const body = node.body?.trim();
    if (!body) continue;
    const heading =
      node.symbol_kind === "file"
        ? `### ${node.file}`
        : `### ${node.label} (${node.symbol_kind || "symbol"})`;
    parts.push(`${heading}\n\n${body}`);
  }

  return unique(parts).join("\n\n---\n\n").slice(0, 24_000);
}

function aggregateEdgeSummary(edges: ChangeEdge[], sourceFile: string, targetFile: string): string {
  const summaries = unique(edges.map((edge) => edge.summary).filter(Boolean));
  if (summaries.length === 0) return `${sourceFile} → ${targetFile}`;
  if (summaries.length === 1) return summaries[0];
  return `${summaries[0]} 외 ${summaries.length - 1}개 관계`;
}

function aggregateEdgeBody(edges: ChangeEdge[], sourceFile: string, targetFile: string): string {
  const bodies = unique(edges.map((edge) => edge.body?.trim()).filter(Boolean));
  if (bodies.length > 0) return bodies.join("\n\n---\n\n").slice(0, 18_000);
  return [
    `- **출발 파일**: \`${sourceFile}\``,
    `- **도착 파일**: \`${targetFile}\``,
    `- **관계**: ${unique(edges.map((edge) => edge.kind)).join(", ")}`,
  ].join("\n");
}

function rankNode(node: ChangeNode): number {
  let score = 0;
  if (node.symbol_kind === "file") score += 10;
  if (node.kind === "changed") score += 5;
  if (node.status !== "unchanged") score += 3;
  score += Math.min(node.added_lines + node.removed_lines, 20) / 20;
  return score;
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function firstNonEmpty(values: string[]): string {
  return values.find((value) => value && value.trim()) ?? "";
}

function unique<T>(values: T[]): T[] {
  return Array.from(new Set(values));
}
