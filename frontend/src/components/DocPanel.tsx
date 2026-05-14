import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import type { ChangeEdge, ChangeGraphResponse, ChangeNode } from "@/types/changes";

interface DocPanelProps {
  graph: ChangeGraphResponse | null;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
}

export function DocPanel({ graph, selectedNodeId, selectedEdgeId }: DocPanelProps) {
  if (!graph) {
    return (
      <div className="flex h-full items-center justify-center px-4 text-center text-[12px] text-slate-500">
        그래프를 불러오면 노드/엣지 문서가 여기에 표시됩니다.
      </div>
    );
  }

  const node = selectedNodeId ? graph.nodes.find((n) => n.id === selectedNodeId) : null;
  const edge = selectedEdgeId ? graph.edges.find((e) => e.id === selectedEdgeId) : null;

  if (node) return <NodeDoc node={node} />;
  if (edge) return <EdgeDoc edge={edge} graph={graph} />;

  return (
    <div className="space-y-3 overflow-y-auto p-3 text-[13px]">
      <div className="text-[11px] uppercase tracking-wider text-slate-500">
        그래프 요약
      </div>
      <div className="grid grid-cols-2 gap-2 text-[12px] text-slate-300">
        <Stat label="노드" value={graph.nodes.length} />
        <Stat label="엣지" value={graph.edges.length} />
        <Stat
          label="변경 파일"
          value={graph.nodes.filter((n) => n.kind === "changed" && n.symbol_kind === "file").length}
        />
        <Stat
          label="영향받음"
          value={graph.nodes.filter((n) => n.kind === "affected").length}
        />
      </div>
      {graph.warnings.length > 0 ? (
        <div className="rounded border border-amber-700/60 bg-amber-950/40 p-2 text-[12px] text-amber-200">
          <div className="mb-1 font-semibold">Warnings</div>
          <ul className="list-disc pl-4">
            {graph.warnings.map((w, i) => (
              <li key={i}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="text-[11px] uppercase tracking-wider text-slate-500">
        노드 목록
      </div>
      <ul className="space-y-1 text-[12px] text-slate-300">
        {graph.nodes.map((n) => (
          <li key={n.id} className="flex items-center gap-2 truncate">
            <span className="rounded bg-slate-800 px-1 text-[10px] text-slate-400">{n.kind}</span>
            <span className="truncate">{n.file}::{n.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-900/70 px-2 py-1">
      <div className="text-[10px] uppercase text-slate-500">{label}</div>
      <div className="text-base font-semibold text-slate-100">{value}</div>
    </div>
  );
}

function NodeDoc({ node }: { node: ChangeNode }) {
  return (
    <div className="flex h-full flex-col overflow-y-auto p-3 text-[13px]">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">node</div>
      <div className="mt-0.5 text-base font-semibold text-slate-100">{node.label}</div>
      <div className="text-[12px] text-slate-400">
        {node.file}
        {node.start_line ? `:${node.start_line}-${node.end_line}` : ""}
      </div>
      <div className="mt-2 flex flex-wrap gap-1 text-[10px]">
        <Pill label={node.kind} />
        <Pill label={node.symbol_kind || "file"} />
        <Pill label={node.status} />
        {node.language ? <Pill label={node.language} /> : null}
        {node.added_lines ? <Pill label={`+${node.added_lines}`} tone="emerald" /> : null}
        {node.removed_lines ? <Pill label={`-${node.removed_lines}`} tone="rose" /> : null}
      </div>
      {node.summary ? (
        <div className="mt-3 text-[13px] font-medium text-slate-200">{node.summary}</div>
      ) : null}
      <div className="markdown-body mt-2">
        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
          {node.body || "_LLM 설명이 비어 있습니다._"}
        </ReactMarkdown>
      </div>
      {node.snippet ? (
        <>
          <div className="mt-4 text-[10px] uppercase tracking-wider text-slate-500">diff 일부</div>
          <pre className="mt-1 max-h-[40vh] overflow-auto rounded bg-slate-950 p-2 text-[11px] leading-snug text-slate-300">
            {node.snippet}
          </pre>
        </>
      ) : null}
    </div>
  );
}

function EdgeDoc({ edge, graph }: { edge: ChangeEdge; graph: ChangeGraphResponse }) {
  const sourceNode = graph.nodes.find((n) => n.id === edge.source);
  const targetNode = graph.nodes.find((n) => n.id === edge.target);
  return (
    <div className="flex h-full flex-col overflow-y-auto p-3 text-[13px]">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">edge</div>
      <div className="mt-0.5 text-base font-semibold text-slate-100">
        {edge.kind} · {edge.label || ""}
      </div>
      <div className="text-[12px] text-slate-400">
        {sourceNode?.label ?? edge.source}
        <span className="mx-1 text-slate-600">→</span>
        {targetNode?.label ?? edge.target}
      </div>
      {edge.summary ? (
        <div className="mt-3 text-[13px] font-medium text-slate-200">{edge.summary}</div>
      ) : null}
      <div className="markdown-body mt-2">
        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>
          {edge.body || "_엣지 설명이 비어 있습니다._"}
        </ReactMarkdown>
      </div>
    </div>
  );
}

function Pill({ label, tone }: { label: string; tone?: "emerald" | "rose" }) {
  const cls =
    tone === "emerald"
      ? "bg-emerald-900/60 text-emerald-200"
      : tone === "rose"
        ? "bg-rose-900/60 text-rose-200"
        : "bg-slate-800 text-slate-200";
  return <span className={`rounded px-1.5 py-0.5 ${cls}`}>{label}</span>;
}
