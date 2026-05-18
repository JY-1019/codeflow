import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import { MessageSquareText } from "lucide-react";
import type { ChangeGraphResponse } from "@/types/changes";

interface NarrativePanelProps {
  graph: ChangeGraphResponse | null;
  assistantResponse: string;
}

/**
 * Read-only narrative pane. Shows:
 *   1. The full assistant response the user pasted in (their LLM's voice).
 *   2. Below it, the paragraphs that didn't map to any node (graph.narrative).
 *      Those are the "general" parts of the response — not tied to a specific file.
 */
export function NarrativePanel({ graph, assistantResponse }: NarrativePanelProps) {
  const hasResponse = assistantResponse.trim().length > 0;
  const hasUnmatched = graph?.narrative?.trim();

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-slate-900/70">
      <div className="flex shrink-0 items-center gap-2 border-b border-slate-800 px-3 py-2 text-[12px] font-semibold uppercase tracking-wider text-slate-400">
        <MessageSquareText className="h-3.5 w-3.5 text-sky-400" />
        AI 응답 · 줄글 설명
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3 text-[13px]">
        {!hasResponse ? (
          <div className="px-1 text-[12px] text-slate-500">
            아래 입력칸에 Codex / Claude Code의 응답을 붙여넣고 <span className="text-slate-300">분석</span>을 누르세요.
            응답의 각 단락이 자동으로 그래프의 노드/엣지와 연결됩니다.
          </div>
        ) : (
          <Section title="원본 응답" body={assistantResponse} />
        )}
        {hasUnmatched ? (
          <Section
            title="노드에 매핑되지 않은 부분"
            body={graph!.narrative}
            tone="dim"
          />
        ) : null}
      </div>
    </div>
  );
}

function Section({
  title,
  body,
  tone,
}: {
  title: string;
  body: string;
  tone?: "dim";
}) {
  return (
    <div>
      <div
        className={`mb-1 text-[10px] uppercase tracking-wider ${
          tone === "dim" ? "text-slate-600" : "text-slate-500"
        }`}
      >
        {title}
      </div>
      <div
        className={`markdown-body rounded border ${
          tone === "dim"
            ? "border-slate-800 bg-slate-950/50 text-slate-400"
            : "border-slate-700 bg-slate-900/70 text-slate-200"
        } px-3 py-2`}
      >
        <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{body}</ReactMarkdown>
      </div>
    </div>
  );
}
