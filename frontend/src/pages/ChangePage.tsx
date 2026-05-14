import { useEffect, useState } from "react";
import { GitBranch, Play, AlertTriangle, RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import { fetchChanges } from "@/api/client";
import { ChangeFlow } from "@/components/ChangeFlow";
import { NarrativePanel } from "@/components/NarrativePanel";
import { DocPanel } from "@/components/DocPanel";
import type { ChangeGraphResponse } from "@/types/changes";

type Source = "working" | "staged" | "range";

const LS_ROOT = "codeflow-light:projectRoot";
const LS_RESPONSE = "codeflow-light:assistantResponse";

export function ChangePage() {
  const [projectRoot, setProjectRoot] = useState<string>(() =>
    localStorage.getItem(LS_ROOT) ?? ""
  );
  const [source, setSource] = useState<Source>("working");
  const [baseRef, setBaseRef] = useState("");
  const [headRef, setHeadRef] = useState("HEAD");
  const [assistantResponse, setAssistantResponse] = useState<string>(() =>
    localStorage.getItem(LS_RESPONSE) ?? ""
  );
  const [responseOpen, setResponseOpen] = useState(true);
  const [graph, setGraph] = useState<ChangeGraphResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  useEffect(() => {
    if (projectRoot) localStorage.setItem(LS_ROOT, projectRoot);
  }, [projectRoot]);

  useEffect(() => {
    localStorage.setItem(LS_RESPONSE, assistantResponse);
  }, [assistantResponse]);

  async function analyze() {
    setError(null);
    if (!projectRoot.trim()) {
      setError("project root를 먼저 입력하세요.");
      return;
    }
    setLoading(true);
    setSelectedNodeId(null);
    setSelectedEdgeId(null);
    try {
      const result = await fetchChanges({
        projectRoot: projectRoot.trim(),
        source,
        baseRef: source === "range" ? baseRef.trim() || undefined : undefined,
        headRef: source === "range" ? headRef.trim() || undefined : undefined,
        assistantResponse,
      });
      setGraph(result);
      setResponseOpen(false);
    } catch (err: unknown) {
      const message =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        (err as Error)?.message ??
        "unknown error";
      setError(String(message));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid h-screen grid-cols-[420px_1fr_400px] grid-rows-[auto_auto_1fr]">
      <header className="col-span-3 flex items-center justify-between border-b border-slate-800 bg-slate-900/80 px-4 py-2">
        <div className="flex items-center gap-2 text-[14px] font-semibold text-slate-100">
          <GitBranch className="h-4 w-4 text-sky-400" />
          Codeflow Light · AI 응답을 변경 그래프로
        </div>
        <div className="flex items-center gap-2 text-[12px]">
          <input
            value={projectRoot}
            onChange={(e) => setProjectRoot(e.target.value)}
            placeholder="/path/to/git/repo"
            className="w-[260px] rounded border border-slate-700 bg-slate-950 px-2 py-1 outline-none focus:border-sky-500"
          />
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as Source)}
            className="rounded border border-slate-700 bg-slate-950 px-2 py-1 outline-none"
          >
            <option value="working">working (HEAD..tree)</option>
            <option value="staged">staged</option>
            <option value="range">range</option>
          </select>
          {source === "range" ? (
            <>
              <input
                value={baseRef}
                onChange={(e) => setBaseRef(e.target.value)}
                placeholder="base ref"
                className="w-[120px] rounded border border-slate-700 bg-slate-950 px-2 py-1 outline-none"
              />
              <input
                value={headRef}
                onChange={(e) => setHeadRef(e.target.value)}
                placeholder="head ref"
                className="w-[120px] rounded border border-slate-700 bg-slate-950 px-2 py-1 outline-none"
              />
            </>
          ) : null}
          <button
            onClick={() => void analyze()}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded bg-sky-600 px-3 py-1 text-white hover:bg-sky-500 disabled:opacity-50"
          >
            {loading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
            분석
          </button>
        </div>
      </header>

      <div className="col-span-3 border-b border-slate-800 bg-slate-950/60">
        <button
          onClick={() => setResponseOpen((v) => !v)}
          className="flex w-full items-center justify-between px-4 py-1.5 text-[11px] uppercase tracking-wider text-slate-400 hover:text-slate-200"
        >
          <span>
            AI 응답 (Codex / Claude Code의 설명){" "}
            {assistantResponse.trim()
              ? `· ${assistantResponse.length}자`
              : "· 비어 있음"}
          </span>
          {responseOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
        {responseOpen ? (
          <div className="px-4 pb-2">
            <textarea
              value={assistantResponse}
              onChange={(e) => setAssistantResponse(e.target.value)}
              placeholder="여기에 Codex / Claude Code의 응답을 그대로 붙여넣으세요. 각 단락이 변경된 노드와 자동으로 연결됩니다."
              rows={5}
              className="w-full resize-y rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-[12px] text-slate-100 outline-none focus:border-sky-500"
            />
          </div>
        ) : null}
      </div>

      {error ? (
        <div className="col-span-3 flex items-center gap-2 border-b border-rose-900/60 bg-rose-950/60 px-3 py-1.5 text-[12px] text-rose-200">
          <AlertTriangle className="h-3.5 w-3.5" />
          {error}
        </div>
      ) : null}

      <aside className="border-r border-slate-800">
        <NarrativePanel graph={graph} assistantResponse={assistantResponse} />
      </aside>

      <main className="relative h-full bg-slate-950">
        {!graph ? (
          <EmptyState />
        ) : (
          <ChangeFlow
            graph={graph}
            selectedNodeId={selectedNodeId}
            selectedEdgeId={selectedEdgeId}
            onSelectNode={setSelectedNodeId}
            onSelectEdge={setSelectedEdgeId}
          />
        )}
      </main>

      <aside className="border-l border-slate-800 bg-slate-900/40">
        <DocPanel
          graph={graph}
          selectedNodeId={selectedNodeId}
          selectedEdgeId={selectedEdgeId}
        />
      </aside>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-slate-400">
      <GitBranch className="h-8 w-8 text-slate-600" />
      <div className="text-[13px]">
        프로젝트 루트 + AI 응답 텍스트를 넣고 <span className="text-sky-300">분석</span>을 누르세요.
      </div>
      <div className="max-w-md text-[12px] text-slate-500">
        백엔드는 LLM을 호출하지 않습니다. Codex/Claude Code가 이미 만든 응답 텍스트를
        변경된 파일·심볼 노드에 매핑해서 시각화합니다.
      </div>
    </div>
  );
}
