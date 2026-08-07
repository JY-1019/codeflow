import { useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  FileText,
  GitCompareArrows,
  Link2,
  RefreshCw,
  Sigma,
} from "lucide-react";
import type { ChangeEdge, ChangeGraphResponse, ChangeNode } from "@/types/changes";

interface ReviewSummaryPanelProps {
  graph: ChangeGraphResponse | null;
  loading: boolean;
  refreshedAt: string | null;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  onSelectNode: (id: string) => void;
  onSelectEdge: (id: string) => void;
}

export function ReviewSummaryPanel({
  graph,
  loading,
  refreshedAt,
  selectedNodeId,
  selectedEdgeId,
  onSelectNode,
  onSelectEdge,
}: ReviewSummaryPanelProps) {
  const summary = graph ? summarizeGraph(graph) : null;
  const [filesOpen, setFilesOpen] = useState(true);
  const [edgesOpen, setEdgesOpen] = useState(true);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-slate-900/70">
      <div className="flex shrink-0 items-center gap-2 border-b border-slate-800 px-3 py-2 text-[12px] font-semibold uppercase tracking-wider text-slate-400">
        <GitCompareArrows className="h-3.5 w-3.5 text-cyan-300" />
        Git diff summary
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-3 text-[13px]">
        {!summary ? (
          <EmptySummary loading={loading} />
        ) : (
          <div className="space-y-4">
            <div className="rounded-md border border-slate-700 bg-slate-950/50 p-3">
              <div className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wider text-slate-500">
                <span>Overview</span>
                {refreshedAt ? (
                  <span className="normal-case tracking-normal text-slate-500">{refreshedAt}</span>
                ) : null}
              </div>
              <p className="mt-2 whitespace-pre-line text-[13px] leading-relaxed text-slate-200">
                {summary.overview}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <StatCard icon={FileText} label="Files" value={summary.fileCount} />
              <StatCard icon={Link2} label="Relations" value={summary.edgeCount} />
              <StatCard icon={Sigma} label="Added" value={`+${summary.added}`} tone="emerald" />
              <StatCard icon={Sigma} label="Removed" value={`-${summary.removed}`} tone="rose" />
            </div>

            <section className="rounded-md border border-slate-800 bg-slate-950/20">
              <SectionToggle
                open={filesOpen}
                title="Changed files"
                count={summary.files.length}
                onToggle={() => setFilesOpen((value) => !value)}
              />
              {filesOpen ? (
                <div className="space-y-2 border-t border-slate-800 p-2">
                  {summary.files.map((node) => (
                    <button
                      key={node.id}
                      onClick={() => onSelectNode(node.id)}
                      className={`w-full rounded-md border px-3 py-2 text-left transition ${
                        selectedNodeId === node.id
                          ? "border-cyan-500 bg-cyan-950/35"
                          : "border-slate-800 bg-slate-950/35 hover:border-slate-600"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="truncate text-[12px] font-semibold text-slate-100">
                          {node.file}
                        </span>
                        <span className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase text-slate-300">
                          {statusLabel(node.status)}
                        </span>
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-[11px]">
                        <span className="text-emerald-300">+{node.added_lines}</span>
                        <span className="text-rose-300">-{node.removed_lines}</span>
                        {node.summary ? (
                          <span className="truncate text-slate-400">{node.summary}</span>
                        ) : null}
                      </div>
                    </button>
                  ))}
                </div>
              ) : null}
            </section>

            <section className="rounded-md border border-slate-800 bg-slate-950/20">
              <SectionToggle
                open={edgesOpen}
                title="Connections"
                count={summary.edges.length}
                onToggle={() => setEdgesOpen((value) => !value)}
              />
              {edgesOpen ? (
                <div className="border-t border-slate-800 p-2">
                  {summary.edges.length === 0 ? (
                    <div className="rounded-md border border-slate-800 bg-slate-950/35 px-3 py-3 text-[12px] text-slate-500">
                      No import relationships were detected between the changed files.
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {summary.edges.map((edge) => (
                        <button
                          key={edge.id}
                          onClick={() => onSelectEdge(edge.id)}
                          className={`w-full rounded-md border px-3 py-2 text-left transition ${
                            selectedEdgeId === edge.id
                              ? "border-sky-500 bg-sky-950/30"
                              : "border-slate-800 bg-slate-950/35 hover:border-slate-600"
                          }`}
                        >
                          <div className="text-[12px] font-medium text-slate-200">
                            {edge.summary || `${edge.source} → ${edge.target}`}
                          </div>
                          <div className="mt-1 text-[10px] uppercase tracking-wider text-slate-500">
                            {edge.kind}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ) : null}
            </section>

            {summary.warnings.length > 0 ? (
              <section className="rounded-md border border-amber-800/70 bg-amber-950/30 p-3 text-[12px] text-amber-200">
                <div className="mb-1 font-semibold">Warnings</div>
                <ul className="list-disc pl-4">
                  {summary.warnings.map((warning, index) => (
                    <li key={index}>{warning}</li>
                  ))}
                </ul>
              </section>
            ) : null}
          </div>
        )}
      </div>
    </div>
  );
}

function SectionToggle({
  open,
  title,
  count,
  onToggle,
}: {
  open: boolean;
  title: string;
  count: number;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-[11px] font-semibold uppercase tracking-wider text-slate-400 hover:text-slate-100"
    >
      <span className="inline-flex items-center gap-1.5">
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        {title}
      </span>
      <span className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
        {count}
      </span>
    </button>
  );
}

function EmptySummary({ loading }: { loading: boolean }) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center text-[12px] text-slate-500">
      <RefreshCw className={`h-5 w-5 ${loading ? "animate-spin text-cyan-300" : "text-slate-600"}`} />
      <div>{loading ? "Summarizing diff..." : "Select Refresh diff to display the branch diff summary here."}</div>
    </div>
  );
}

function StatCard({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: typeof FileText;
  label: string;
  value: number | string;
  tone?: "emerald" | "rose";
}) {
  const valueClass =
    tone === "emerald"
      ? "text-emerald-200"
      : tone === "rose"
        ? "text-rose-200"
        : "text-slate-100";

  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/45 px-2 py-2">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className={`mt-1 text-lg font-semibold ${valueClass}`}>{value}</div>
    </div>
  );
}

function summarizeGraph(graph: ChangeGraphResponse) {
  const files = graph.nodes
    .filter((node) => node.kind === "changed" && node.symbol_kind === "file")
    .sort(compareByChangeWeight);

  return {
    files,
    fileCount: files.length,
    edgeCount: graph.edges.length,
    added: sum(files.map((node) => node.added_lines)),
    removed: sum(files.map((node) => node.removed_lines)),
    edges: graph.edges.slice().sort(compareEdges),
    warnings: graph.warnings,
    overview: buildOverview(files, graph.edges),
  };
}

function buildOverview(files: ChangeNode[], edges: ChangeEdge[]): string {
  if (files.length === 0) {
    return "No files were changed directly in the current branch diff.";
  }

  const added = sum(files.map((node) => node.added_lines));
  const removed = sum(files.map((node) => node.removed_lines));
  const areas = describeAreas(files);
  const mainFiles = files
    .slice(0, 3)
    .map((node) => node.file)
    .join(", ");
  const relationText =
    edges.length > 0
      ? `${edges.length} connection${edges.length === 1 ? " was" : "s were"} detected. See Connections below for import details.`
      : "No direct import connections were detected between the changed files.";

  return [
    `Changed ${files.length} file${files.length === 1 ? "" : "s"}, mainly in ${areas}.`,
    `Total line changes are +${added}/-${removed}; the largest change${files.length === 1 ? " is" : "s are"} in ${mainFiles}.`,
    relationText,
  ].join("\n");
}

function describeAreas(files: ChangeNode[]): string {
  const areaCounts = new Map<string, number>();
  for (const file of files) {
    const area = areaLabel(file.file);
    areaCounts.set(area, (areaCounts.get(area) ?? 0) + 1);
  }

  return Array.from(areaCounts.entries())
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 3)
    .map(([label, count]) => `${label} (${count})`)
    .join(", ");
}

function areaLabel(file: string): string {
  if (file.startsWith("frontend/src/components/")) return "frontend components";
  if (file.startsWith("frontend/src/pages/")) return "frontend pages";
  if (file.startsWith("frontend/src/")) return "frontend logic";
  if (file.startsWith("backend/app/services/")) return "backend services";
  if (file.startsWith("backend/app/routers/")) return "backend API";
  if (file.startsWith("backend/tests/")) return "backend tests";
  if (file.startsWith("skill/")) return "skills";
  if (file.endsWith(".md")) return "documentation";
  return file.split("/")[0] || "other files";
}

function compareByChangeWeight(a: ChangeNode, b: ChangeNode): number {
  const delta =
    b.added_lines + b.removed_lines - (a.added_lines + a.removed_lines);
  if (delta !== 0) return delta;
  return a.file.localeCompare(b.file);
}

function compareEdges(a: ChangeEdge, b: ChangeEdge): number {
  return (a.summary || a.id).localeCompare(b.summary || b.id);
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}

function statusLabel(status: string): string {
  if (status === "added") return "Added";
  if (status === "modified") return "Modified";
  if (status === "deleted") return "Deleted";
  if (status === "renamed") return "Renamed";
  return status;
}
