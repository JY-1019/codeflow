import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
} from "react";
import {
  GitBranch,
  AlertTriangle,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  PanelLeftClose,
  PanelLeftOpen,
  BarChart3,
  CheckCircle2,
  CircleDashed,
  Code2,
  FileText,
  GitCommitHorizontal,
  GitMerge,
  GitPullRequestArrow,
  SearchCheck,
  Wrench,
  type LucideIcon,
} from "lucide-react";
import { fetchCodexUsage, fetchLatestChanges, fetchLatestSession } from "@/api/client";
import { SessionFlow, type SessionGroupFocusTarget } from "@/components/SessionFlow";
import { DocPanel } from "@/components/DocPanel";
import { toFileGraphResponse } from "@/flow/utils/fileGraph";
import type {
  ChangeGraphResponse,
  ChangeGroup,
  ChangeSessionResponse,
  CodexRateLimitWindow,
  CodexRateLimits,
  CodexUsageResponse,
  MarkdownWorkflowRun,
  MarkdownWorkflowStep,
  MarkdownWorkflowStepKind,
  MarkdownWorkflowStepStatus,
} from "@/types/changes";

const LS_ROOT = "codeflow:projectRoot";
const LS_RESPONSE = "codeflow:assistantResponse";
const LS_NARRATIVE_OPEN = "codeflow:narrativeOpen";
const LS_DOC_PANEL_WIDTH = "codeflow:docPanelWidth";
const DOC_PANEL_DEFAULT_WIDTH = 500;
const DOC_PANEL_MIN_WIDTH = 340;
const DOC_PANEL_MAX_WIDTH = 780;
const POLL_MS = 2_000;
const WINDOW_PARAMS = new URLSearchParams(window.location.search);
const WINDOW_SESSION_ID = WINDOW_PARAMS.get("session_id")?.trim() ?? "";
const WINDOW_SESSION_TITLE = WINDOW_PARAMS.get("session_title")?.trim() ?? "";
const WINDOW_PROJECT_ROOT = WINDOW_PARAMS.get("project_root")?.trim() ?? "";
const RESPONSE_STORAGE_KEY = WINDOW_SESSION_ID
  ? `${LS_RESPONSE}:${WINDOW_SESSION_ID}`
  : LS_RESPONSE;

export function ChangePage() {
  const [projectRoot, setProjectRoot] = useState<string>(() =>
    WINDOW_PROJECT_ROOT || localStorage.getItem(LS_ROOT) || ""
  );
  const [assistantResponse, setAssistantResponse] = useState<string>(() =>
    localStorage.getItem(RESPONSE_STORAGE_KEY) ?? ""
  );
  const [responseInputOpen, setResponseInputOpen] = useState(false);
  const [narrativeOpen, setNarrativeOpen] = useState<boolean>(() => {
    const stored = localStorage.getItem(LS_NARRATIVE_OPEN);
    return stored === null ? true : stored === "true";
  });
  const [docPanelWidth, setDocPanelWidth] = useState<number>(() => {
    const stored = Number(localStorage.getItem(LS_DOC_PANEL_WIDTH));
    return Number.isFinite(stored) && stored > 0
      ? clamp(stored, DOC_PANEL_MIN_WIDTH, DOC_PANEL_MAX_WIDTH)
      : DOC_PANEL_DEFAULT_WIDTH;
  });
  const [graph, setGraph] = useState<ChangeGraphResponse | null>(null);
  const [session, setSession] = useState<ChangeSessionResponse | null>(null);
  const [activeGroupId, setActiveGroupId] = useState<string | null>(null);
  const [selectedGroupId, setSelectedGroupId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);
  const [sessionFocusTarget, setSessionFocusTarget] = useState<SessionGroupFocusTarget | null>(null);
  const [codexUsage, setCodexUsage] = useState<CodexUsageResponse | null>(null);
  const [usageLoading, setUsageLoading] = useState(false);
  const didInitialLoadRef = useRef(false);
  const latestGroupRef = useRef<string | null>(null);

  useEffect(() => {
    if (projectRoot && !WINDOW_PROJECT_ROOT) localStorage.setItem(LS_ROOT, projectRoot);
  }, [projectRoot]);

  useEffect(() => {
    localStorage.setItem(RESPONSE_STORAGE_KEY, assistantResponse);
  }, [assistantResponse]);

  useEffect(() => {
    localStorage.setItem(LS_NARRATIVE_OPEN, String(narrativeOpen));
  }, [narrativeOpen]);

  useEffect(() => {
    localStorage.setItem(LS_DOC_PANEL_WIDTH, String(docPanelWidth));
  }, [docPanelWidth]);

  const activeGroup = useMemo(
    () => findGroup(session, activeGroupId) ?? latestGroup(session),
    [activeGroupId, session]
  );
  const selectedGroup = useMemo(
    () => findGroup(session, selectedGroupId),
    [selectedGroupId, session]
  );
  const selectedWorkflowStep = useMemo(
    () => findWorkflowStep(session, selectedNodeId),
    [selectedNodeId, session]
  );
  const workflowStats = useMemo(() => buildWorkflowStats(session), [session]);

  const activeGroupGraph = useMemo(
    () => (activeGroup ? toFileGraphResponse(activeGroup.graph) : null),
    [activeGroup]
  );
  const fallbackGraph = useMemo(
    () => (graph ? toFileGraphResponse(graph) : null),
    [graph]
  );
  const docGraph = activeGroupGraph ?? fallbackGraph;
  const sessionLabel =
    WINDOW_SESSION_TITLE ||
    (codexUsage?.current_session?.id === WINDOW_SESSION_ID
      ? codexUsage.current_session.thread_name
      : "") ||
    shortSessionLabel(WINDOW_SESSION_ID);

  const loadLatestChanges = useCallback(
    async (projectRootOverride?: string) => {
      const latest = await fetchLatestChanges(
        projectRoot.trim() || projectRootOverride || undefined
      );
      setGraph(latest);
      if (!projectRoot && latest.project_root) {
        setProjectRoot(latest.project_root);
      }
      if (!assistantResponse && latest.assistant_response) {
        setAssistantResponse(latest.assistant_response);
      }
      return latest;
    },
    [assistantResponse, projectRoot]
  );

  const loadSession = useCallback(
    async (preferLatest = false) => {
      const result = await fetchLatestSession(
        projectRoot.trim() || undefined,
        WINDOW_SESSION_ID || undefined
      );
      setSession(result);
      if (!projectRoot && result.project_root) {
        setProjectRoot(result.project_root);
      }
      if (result.latest_group_id && (preferLatest || latestGroupRef.current !== result.latest_group_id)) {
        setActiveGroupId(result.latest_group_id);
        setSelectedGroupId(result.latest_group_id);
        setSelectedNodeId(null);
        setSelectedEdgeId(null);
        setSessionFocusTarget({ groupId: result.latest_group_id, nonce: Date.now() });
        await loadLatestChanges(result.project_root);
        latestGroupRef.current = result.latest_group_id;
      }
      return result;
    },
    [loadLatestChanges, projectRoot]
  );

  const loadCodexUsage = useCallback(async () => {
    setUsageLoading(true);
    try {
      const result = await fetchCodexUsage(projectRoot.trim() || undefined);
      setCodexUsage(result);
    } catch {
      setCodexUsage(null);
    } finally {
      setUsageLoading(false);
    }
  }, [projectRoot]);

  const refreshSession = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      await loadSession(true);
      await loadCodexUsage();
    } catch (err: unknown) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [loadCodexUsage, loadSession]);

  const startDocPanelResize = useCallback(
    (event: ReactPointerEvent<HTMLDivElement>) => {
      event.preventDefault();
      const startX = event.clientX;
      const startWidth = docPanelWidth;
      const previousCursor = document.body.style.cursor;
      const previousUserSelect = document.body.style.userSelect;
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const handlePointerMove = (moveEvent: PointerEvent) => {
        const delta = startX - moveEvent.clientX;
        setDocPanelWidth(clamp(startWidth + delta, DOC_PANEL_MIN_WIDTH, DOC_PANEL_MAX_WIDTH));
      };
      const cleanup = () => {
        document.body.style.cursor = previousCursor;
        document.body.style.userSelect = previousUserSelect;
        window.removeEventListener("pointermove", handlePointerMove);
      };

      window.addEventListener("pointermove", handlePointerMove);
      window.addEventListener("pointerup", cleanup, { once: true });
    },
    [docPanelWidth]
  );

  useEffect(() => {
    if (didInitialLoadRef.current) return;
    didInitialLoadRef.current = true;
    (async () => {
      setLoading(true);
      try {
        const sessionResult = await loadSession(true);
        if (!sessionResult.latest_group_id) {
          await loadLatestChanges(sessionResult.project_root);
        }
        await loadCodexUsage();
      } catch (err: unknown) {
        setError(errorMessage(err));
      } finally {
        setLoading(false);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const timer = window.setInterval(() => {
      void loadSession(false).catch((err: unknown) => setError(errorMessage(err)));
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [loadSession]);

  useEffect(() => {
    void loadCodexUsage();
    const timer = window.setInterval(() => {
      void loadCodexUsage();
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [loadCodexUsage]);

  const narrativeColumn = narrativeOpen ? "340px" : "44px";

  return (
    <div
      className="grid h-screen min-h-0 overflow-hidden"
      style={{
        gridTemplateColumns: `${narrativeColumn} 1fr ${docPanelWidth}px`,
        gridTemplateRows: error
          ? "auto auto auto auto minmax(0, 1fr)"
          : "auto auto auto minmax(0, 1fr)",
      }}
    >
      <header className="col-span-3 flex items-center justify-between border-b border-slate-800 bg-slate-900/80 px-4 py-2">
        <div className="flex items-center gap-2 text-[14px] font-semibold text-slate-100">
          <GitBranch className="h-4 w-4 text-cyan-300" />
          Codeflow
          {sessionLabel ? (
            <span
              className="max-w-[320px] truncate rounded bg-slate-800 px-1.5 py-0.5 text-[10px] font-medium text-slate-300"
              title={sessionLabel}
            >
              {sessionLabel}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2 text-[12px]">
          <input
            value={projectRoot}
            onChange={(e) => setProjectRoot(e.target.value)}
            placeholder="project root"
            className="w-[260px] rounded border border-slate-700 bg-slate-950 px-2 py-1 outline-none focus:border-cyan-500"
          />
          <button
            onClick={() => void refreshSession()}
            disabled={loading}
            className="inline-flex items-center gap-1 rounded bg-cyan-600 px-3 py-1 text-white hover:bg-cyan-500 disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh session
          </button>
        </div>
      </header>

      <div className="col-span-3 border-b border-slate-800 bg-slate-950/60">
        <button
          onClick={() => setResponseInputOpen((v) => !v)}
          className="flex w-full items-center justify-between px-4 py-1.5 text-[11px] uppercase tracking-wider text-slate-400 hover:text-slate-200"
        >
          <span>
            Manual capture text{" "}
            {assistantResponse.trim()
              ? `· ${assistantResponse.length} character${assistantResponse.length === 1 ? "" : "s"}`
              : "· Filled automatically by event/capture"}
            <CodexUsageInline usage={codexUsage} loading={usageLoading} />
          </span>
          {responseInputOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
        {responseInputOpen ? (
          <div className="space-y-2 px-4 pb-2">
            <CodexUsagePanel
              usage={codexUsage}
              loading={usageLoading}
              onRefresh={() => void loadCodexUsage()}
            />
            <textarea
              value={assistantResponse}
              onChange={(e) => setAssistantResponse(e.target.value)}
            placeholder="Response text for legacy capture"
              rows={4}
              className="w-full resize-y rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-[12px] text-slate-100 outline-none focus:border-cyan-500"
            />
          </div>
        ) : null}
      </div>

      <WorkflowOverviewBar
        session={session}
        activeGroup={activeGroup}
        selectedWorkflowStep={selectedWorkflowStep}
        stats={workflowStats}
      />

      {error ? (
        <div className="col-span-3 flex items-center gap-2 border-b border-rose-900/60 bg-rose-950/60 px-3 py-1.5 text-[12px] text-rose-200">
          <AlertTriangle className="h-3.5 w-3.5" />
          {error}
        </div>
      ) : null}

      <aside className="relative flex h-full min-h-0 flex-col overflow-hidden border-r border-slate-800">
        <button
          onClick={() => setNarrativeOpen((v) => !v)}
          className="absolute right-1 top-1 z-10 inline-flex h-7 w-7 items-center justify-center rounded text-slate-400 hover:bg-slate-700/60 hover:text-slate-100"
          title={narrativeOpen ? "Collapse panel" : "Expand panel"}
        >
          {narrativeOpen ? (
            <PanelLeftClose className="h-3.5 w-3.5" />
          ) : (
            <PanelLeftOpen className="h-3.5 w-3.5" />
          )}
        </button>
        {narrativeOpen ? (
          <SessionPanel
            session={session}
            activeGroupId={activeGroup?.id ?? null}
            stats={workflowStats}
            onSelectGroup={(groupId) => {
              setActiveGroupId(groupId);
              setSelectedGroupId(groupId);
              setSelectedNodeId(null);
              setSelectedEdgeId(null);
              setSessionFocusTarget({ groupId, nonce: Date.now() });
            }}
          />
        ) : (
          <div className="flex h-full min-h-0 flex-col items-center pt-10 text-[10px] uppercase tracking-widest text-slate-500">
            <span className="vertical-text">Flow</span>
          </div>
        )}
      </aside>

      <main className="relative h-full min-h-0 overflow-hidden bg-slate-950">
        <SessionFlow
          session={session}
          activeGroupId={activeGroup?.id ?? null}
          selectedGroupId={selectedGroupId}
          selectedNodeId={selectedNodeId}
          selectedEdgeId={selectedEdgeId}
          focusTarget={sessionFocusTarget}
          onSelectGroup={(groupId) => {
            setActiveGroupId(groupId);
            setSelectedGroupId(groupId);
            setSelectedNodeId(null);
            setSelectedEdgeId(null);
            setSessionFocusTarget(null);
          }}
          onSelectNode={(groupId, nodeId) => {
            setActiveGroupId(groupId);
            setSelectedGroupId(null);
            setSelectedNodeId(nodeId);
            setSelectedEdgeId(null);
            setSessionFocusTarget(null);
          }}
          onSelectEdge={(groupId, edgeId) => {
            setActiveGroupId(groupId);
            setSelectedGroupId(null);
            setSelectedNodeId(null);
            setSelectedEdgeId(edgeId);
            setSessionFocusTarget(null);
          }}
        />
      </main>

      <aside className="relative h-full min-h-0 min-w-0 overflow-hidden border-l border-slate-800 bg-slate-900/40">
        <div
          onPointerDown={startDocPanelResize}
          className="absolute left-0 top-0 z-20 h-full w-2 cursor-col-resize touch-none bg-transparent hover:bg-cyan-400/25"
          title="Resize document panel"
        />
        <DocPanel
          graph={docGraph}
          selectedWorkflowStep={selectedWorkflowStep}
          selectedGroup={selectedGroup}
          selectedNodeId={selectedNodeId}
          selectedEdgeId={selectedEdgeId}
        />
      </aside>
    </div>
  );
}

interface WorkflowStats {
  markdownRuns: number;
  workflowSteps: number;
  implementationSteps: number;
  reviewSteps: number;
  reviewFixSteps: number;
  verificationSteps: number;
  completedSteps: number;
  pendingSteps: number;
  blockedSteps: number;
  changedFiles: number;
  addedLines: number;
  removedLines: number;
}

interface SelectedWorkflowStepDetails {
  group: ChangeGroup;
  run: MarkdownWorkflowRun | null;
  step: MarkdownWorkflowStep;
  nodeId: string;
}

function WorkflowOverviewBar({
  session,
  activeGroup,
  selectedWorkflowStep,
  stats,
}: {
  session: ChangeSessionResponse | null;
  activeGroup: ChangeGroup | null;
  selectedWorkflowStep: SelectedWorkflowStepDetails | null;
  stats: WorkflowStats;
}) {
  const primaryRun = selectedWorkflowStep?.run ?? activeGroup?.workflow_runs?.[0] ?? null;
  const primarySteps = primaryRun?.steps ?? [];
  const selectedStep = selectedWorkflowStep?.step ?? null;
  const branch = session?.branch || "Unknown branch";
  const activeTitle = activeGroup
    ? `Request ${activeGroup.sequence ?? ""} · ${activeGroup.name}`
    : "Waiting for capture";

  return (
    <div className="col-span-3 border-b border-slate-800 bg-slate-900/65 px-4 py-2">
      <div className="grid gap-3 xl:grid-cols-[minmax(220px,0.9fr)_minmax(420px,1.6fr)_minmax(320px,1fr)]">
        <div className="min-w-0">
          <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
            Review loop session
          </div>
          <div className="mt-0.5 truncate text-[13px] font-semibold text-slate-100" title={activeTitle}>
            {activeTitle}
          </div>
          <div className="mt-1 flex min-w-0 items-center gap-2 text-[11px] text-slate-500">
            <GitBranch className="h-3 w-3 shrink-0 text-cyan-300" />
            <span className="truncate" title={branch}>{branch}</span>
            <span className="shrink-0 text-emerald-300">+{stats.addedLines}</span>
            <span className="shrink-0 text-rose-300">-{stats.removedLines}</span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 md:grid-cols-6">
          <OverviewMetric icon={FileText} label="MD" value={stats.markdownRuns} />
          <OverviewMetric icon={Code2} label="Implementation" value={stats.implementationSteps} />
          <OverviewMetric icon={SearchCheck} label="Review" value={stats.reviewSteps} />
          <OverviewMetric icon={Wrench} label="Fixes" value={stats.reviewFixSteps} />
          <OverviewMetric icon={CheckCircle2} label="Verification" value={stats.verificationSteps} />
          <OverviewMetric icon={GitCommitHorizontal} label="Files" value={stats.changedFiles} />
        </div>

        <div className="min-w-0 rounded-md border border-slate-800 bg-slate-950/45 px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0">
              <div className="truncate text-[11px] font-semibold text-slate-200" title={primaryRun?.markdown_title || primaryRun?.markdown_path || selectedStep?.label}>
                {selectedStep ? selectedStep.label : primaryRun?.markdown_title || primaryRun?.markdown_path || "No step selected"}
              </div>
              <div className="mt-0.5 truncate text-[10px] text-slate-500" title={primaryRun?.markdown_path || primaryRun?.command_label || ""}>
                {selectedStep ? stepKindLabel(selectedStep.kind) : workflowSkillLabel(primaryRun?.skill ?? "", primaryRun?.skill_label) || "Workflow"}
              </div>
            </div>
            <div className="shrink-0 text-right text-[10px] text-slate-500">
              <div>{stats.completedSteps}/{stats.workflowSteps || 0} completed</div>
              <div className={stats.blockedSteps ? "text-rose-300" : "text-slate-600"}>
                {stats.blockedSteps ? `${stats.blockedSteps} blocked` : `${stats.pendingSteps} pending`}
              </div>
            </div>
          </div>
          <StepStatusRail steps={primarySteps} compact />
        </div>
      </div>
    </div>
  );
}

function OverviewMetric({
  icon: Icon,
  label,
  value,
}: {
  icon: LucideIcon;
  label: string;
  value: number;
}) {
  return (
    <div className="min-w-0 rounded-md border border-slate-800 bg-slate-950/45 px-2 py-1.5">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-slate-500">
        <Icon className="h-3 w-3 shrink-0 text-cyan-300" />
        <span className="truncate">{label}</span>
      </div>
      <div className="mt-0.5 text-[15px] font-semibold text-slate-100">{value}</div>
    </div>
  );
}

function CodexUsageInline({
  usage,
  loading,
}: {
  usage: CodexUsageResponse | null;
  loading: boolean;
}) {
  if (loading && !usage) {
    return <span className="ml-2 text-slate-500">· Loading Codex usage</span>;
  }
  if (!usage?.available) {
    return <span className="ml-2 text-slate-500">· No Codex usage</span>;
  }
  return (
    <span className="ml-2 text-slate-500">
      · All time {formatTokens(usage.all_time.total_tokens)}
      {usage.current_session
        ? ` · Current session ${formatTokens(usage.current_session.usage.total_tokens)}`
        : ""}
      {usage.rate_limits ? ` · Limits ${formatLimitInline(usage.rate_limits)}` : ""}
    </span>
  );
}

function CodexUsagePanel({
  usage,
  loading,
  onRefresh,
}: {
  usage: CodexUsageResponse | null;
  loading: boolean;
  onRefresh: () => void;
}) {
  const current = usage?.current_session;
  const limits = usage?.rate_limits ?? current?.rate_limits ?? null;
  return (
    <div className="rounded-md border border-slate-800 bg-slate-900/70 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <BarChart3 className="h-3.5 w-3.5 text-cyan-300" />
          Codex usage
        </div>
        <button
          onClick={onRefresh}
          disabled={loading}
          className="inline-flex h-6 w-6 items-center justify-center rounded text-slate-400 hover:bg-slate-800 hover:text-slate-100 disabled:opacity-50"
          title="Refresh Codex usage"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${loading ? "animate-spin" : ""}`} />
        </button>
      </div>
      {usage?.available ? (
        <>
          <div className="grid grid-cols-2 gap-2">
            <UsageCard
              label="All time"
              value={usage.all_time.total_tokens}
              detail={usageDetail(usage.all_time)}
            />
            <UsageCard
              label="Current session"
              value={current?.usage.total_tokens ?? 0}
              detail={current ? usageDetail(current.usage) : "No matching session"}
            />
          </div>
          {limits ? <RateLimitSummary limits={limits} /> : null}
          <div className="mt-2 truncate text-[11px] text-slate-500">
            {current?.thread_name || current?.id || "Codex session"} ·{" "}
            Scanned {usage.scanned_sessions} local session{usage.scanned_sessions === 1 ? "" : "s"}
          </div>
        </>
      ) : (
        <div className="text-[12px] text-slate-500">
          No local Codex usage found yet.
          {usage?.warnings?.[0] ? ` ${usage.warnings[0]}` : ""}
        </div>
      )}
    </div>
  );
}

function RateLimitSummary({ limits }: { limits: CodexRateLimits }) {
  return (
    <div className="mt-2 rounded border border-slate-800 bg-slate-950/45 p-2.5">
      <div className="mb-2 flex items-center justify-between gap-2">
        <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
          Codex limits
        </div>
        {limits.plan_type ? (
          <div className="rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
            {limits.plan_type}
          </div>
        ) : null}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <RateLimitCard label="Primary" window={limits.primary} />
        <RateLimitCard label="Secondary" window={limits.secondary} />
      </div>
    </div>
  );
}

function RateLimitCard({
  label,
  window,
}: {
  label: string;
  window: CodexRateLimitWindow | null;
}) {
  return (
    <div className="rounded border border-slate-800 bg-slate-900/60 px-2 py-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">
        {label} · {formatWindow(window?.window_minutes)}
      </div>
      <div className="mt-1 text-base font-semibold text-cyan-100">
        {formatPercent(window?.used_percent)}
      </div>
      <div className="mt-0.5 truncate text-[10px] text-slate-500">
        reset {formatReset(window?.resets_at)}
      </div>
    </div>
  );
}

function UsageCard({
  label,
  value,
  detail,
}: {
  label: string;
  value: number;
  detail: string;
}) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950/55 px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-1 text-lg font-semibold text-slate-100">{formatTokens(value)}</div>
      <div className="mt-0.5 truncate text-[10px] text-slate-500">{detail}</div>
    </div>
  );
}

function SessionPanel({
  session,
  activeGroupId,
  stats,
  onSelectGroup,
}: {
  session: ChangeSessionResponse | null;
  activeGroupId: string | null;
  stats: WorkflowStats;
  onSelectGroup: (groupId: string) => void;
}) {
  const summary = session?.summary;
  const reviewLoopText = stats.reviewSteps > 0
    ? `${stats.reviewFixSteps}/${stats.reviewSteps}`
    : "-";

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-slate-900/70">
      <div className="shrink-0 border-b border-slate-800 px-3 py-2">
        <div className="text-[12px] font-semibold uppercase tracking-wider text-slate-400">
          Markdown tasks
        </div>
        {summary ? (
          <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-slate-300">
            <MiniStat label="Groups" value={session?.groups.length ?? 0} />
            <MiniStat label="Markdown" value={stats.markdownRuns} />
            <MiniStat label="Fixes" value={reviewLoopText} />
            <MiniStat label="Files" value={stats.changedFiles} />
          </div>
        ) : null}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {!session || session.groups.length === 0 ? (
          <div className="px-2 py-8 text-center text-[12px] text-slate-500">
            Waiting for workflow events
          </div>
        ) : (
          <div className="space-y-2">
            {session.groups.map((group) => (
              <button
                key={group.id}
                onClick={() => onSelectGroup(group.id)}
                title="Show this group in the main flow"
                className={`w-full rounded-md border px-3 py-2 text-left transition ${
                  group.id === activeGroupId
                    ? "border-cyan-500 bg-cyan-950/35"
                    : "border-slate-800 bg-slate-950/35 hover:border-slate-600"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="truncate text-[12px] font-semibold text-slate-100">
                      Group {group.sequence ?? ""} · {group.name}
                    </div>
                  </div>
                  <span className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300">
                    {group.phase_label ?? "Implementation"}
                  </span>
                </div>
                <div className="mt-1 line-clamp-2 text-[11px] leading-snug text-slate-400">
                  {group.summary?.implementation?.[0] ||
                    group.summary?.review?.[0] ||
                    group.user_prompt ||
                    "No user prompt"}
                </div>
                <div className="mt-1 flex items-center gap-2 text-[10px] text-slate-500">
                  <span>{group.summary?.file_count ?? 0} file{group.summary?.file_count === 1 ? "" : "s"}</span>
                  {group.workflow_runs?.length ? <span>{group.workflow_runs.length} loop{group.workflow_runs.length === 1 ? "" : "s"}</span> : null}
                  <span className="text-emerald-300">+{group.summary?.added_lines ?? 0}</span>
                  <span className="text-rose-300">-{group.summary?.removed_lines ?? 0}</span>
                </div>
                {group.workflow_runs?.length ? (
                  <div className="mt-2 space-y-2">
                    {group.workflow_runs.slice(0, 3).map((run) => (
                      <WorkflowRunPreview key={run.id} run={run} />
                    ))}
                  </div>
                ) : null}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded border border-slate-800 bg-slate-950/45 px-2 py-1.5">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className="mt-0.5 text-[13px] font-semibold text-slate-100">{value}</div>
    </div>
  );
}

function WorkflowRunPreview({ run }: { run: MarkdownWorkflowRun }) {
  const title = run.markdown_title || run.markdown_path || run.command_label || run.skill_label;
  return (
    <div className="rounded border border-slate-800 bg-slate-900/55 px-2 py-2">
      <div className="flex items-start gap-2">
        <FileText className="mt-0.5 h-3.5 w-3.5 shrink-0 text-sky-300" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-[11px] font-semibold text-slate-200" title={title}>
            {title}
          </div>
          <div className="mt-0.5 truncate text-[10px] text-slate-500" title={run.markdown_path || run.branch_name}>
            {run.markdown_path || run.branch_name || workflowSkillLabel(run.skill, run.skill_label)}
          </div>
        </div>
        <span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] ${runStatusClass(run.status)}`}>
          {runStatusLabel(run.status)}
        </span>
      </div>
      <StepStatusRail steps={run.steps} />
    </div>
  );
}

function StepStatusRail({
  steps,
  compact = false,
}: {
  steps: MarkdownWorkflowStep[];
  compact?: boolean;
}) {
  if (steps.length === 0) {
    return (
      <div className="mt-2 h-1.5 rounded bg-slate-800" />
    );
  }
  return (
    <div className={`mt-2 flex min-w-0 ${compact ? "gap-1" : "gap-1.5"}`}>
      {steps.map((step) => {
        const Icon = stepIcon(step.kind);
        return (
          <div
            key={`${step.kind}-${step.id}`}
            className={`flex min-w-0 flex-1 items-center justify-center rounded ${compact ? "h-5" : "h-6"} ${statusRailClass(step.status)}`}
            title={`${stepKindLabel(step.kind)} · ${statusLabel(step.status)} · ${step.summary}`}
          >
            <Icon className={compact ? "h-3 w-3" : "h-3.5 w-3.5"} />
          </div>
        );
      })}
    </div>
  );
}

function findGroup(
  session: ChangeSessionResponse | null,
  groupId: string | null
): ChangeGroup | null {
  if (!session || !groupId) return null;
  return session.groups.find((group) => group.id === groupId) ?? null;
}

function findWorkflowStep(
  session: ChangeSessionResponse | null,
  nodeId: string | null
): SelectedWorkflowStepDetails | null {
  if (!session || !nodeId) return null;
  const parts = nodeId.split("::");
  if (parts[0] !== "step" || parts.length < 5) return null;
  const group = findGroup(session, parts[1]);
  if (!group) return null;

  const runId = parts[2];
  const stepIndex = Number(parts[3]);
  const stepId = parts.slice(4).join("::");
  const run = (group.workflow_runs ?? []).find((item) => item.id === runId) ?? null;
  const step = run
    ? run.steps[stepIndex] ?? run.steps.find((item) => item.id === stepId)
    : fallbackWorkflowStep(group);
  if (!step) return null;

  return { group, run, step, nodeId };
}

function fallbackWorkflowStep(group: ChangeGroup): MarkdownWorkflowStep {
  const phase = group.phase ?? "implementation";
  const kind: MarkdownWorkflowStepKind =
    phase === "review" || phase === "review_fix" || phase === "verification"
      ? phase
      : "implementation";
  return {
    id: group.id,
    kind,
    label: group.phase_label ?? phaseLabel(phase),
    summary: fallbackStepSummary(group, kind),
    detail: "",
    status: "completed",
    files: group.summary?.changed_files ?? [],
  };
}

function fallbackStepSummary(group: ChangeGroup, kind: MarkdownWorkflowStepKind): string {
  if (kind === "review" || kind === "review_fix" || kind === "verification") {
    return (
      group.summary?.review?.[0] ||
      group.summary?.implementation?.[0] ||
      "No review or verification details have been recorded for this step yet."
    );
  }
  return (
    group.summary?.implementation?.[0] ||
    group.summary?.review?.[0] ||
    "No implementation details have been recorded for this step yet."
  );
}

function buildWorkflowStats(session: ChangeSessionResponse | null): WorkflowStats {
  const groups = session?.groups ?? [];
  const runs = groups.flatMap((group) => group.workflow_runs ?? []);
  const steps = runs.flatMap((run) => run.steps);
  const files = new Set<string>();
  let addedLines = 0;
  let removedLines = 0;

  groups.forEach((group) => {
    (group.summary?.changed_files ?? []).forEach((file) => files.add(file));
    addedLines += group.summary?.added_lines ?? 0;
    removedLines += group.summary?.removed_lines ?? 0;
  });

  return {
    markdownRuns: runs.length,
    workflowSteps: steps.length,
    implementationSteps: steps.filter((step) => step.kind === "implementation").length,
    reviewSteps: steps.filter((step) => step.kind === "review").length,
    reviewFixSteps: steps.filter((step) => step.kind === "review_fix").length,
    verificationSteps: steps.filter((step) => step.kind === "verification").length,
    completedSteps: steps.filter((step) => step.status === "completed" || step.status === "skipped").length,
    pendingSteps: steps.filter((step) => step.status === "pending" || step.status === "unknown").length,
    blockedSteps: steps.filter((step) => step.status === "blocked").length,
    changedFiles: files.size || session?.summary?.changed_files.length || 0,
    addedLines,
    removedLines,
  };
}

function stepIcon(kind: MarkdownWorkflowStepKind): LucideIcon {
  if (kind === "markdown") return FileText;
  if (kind === "branch") return GitBranch;
  if (kind === "review") return SearchCheck;
  if (kind === "review_fix") return Wrench;
  if (kind === "verification") return CheckCircle2;
  if (kind === "commit") return GitCommitHorizontal;
  if (kind === "push") return GitPullRequestArrow;
  if (kind === "merge") return GitMerge;
  if (kind === "preflight") return CircleDashed;
  return Code2;
}

function stepKindLabel(kind: MarkdownWorkflowStepKind): string {
  if (kind === "preflight") return "Preflight";
  if (kind === "markdown") return "Markdown";
  if (kind === "branch") return "Branch";
  if (kind === "implementation") return "Implementation";
  if (kind === "review") return "Review";
  if (kind === "review_fix") return "Review fix";
  if (kind === "verification") return "Verification";
  if (kind === "commit") return "Commit";
  if (kind === "push") return "Push";
  if (kind === "merge") return "Merge";
  return kind;
}

function workflowSkillLabel(skill: string, label?: string): string {
  const cleaned = label?.trim() || skill.trim();
  const known: Record<string, string> = {
    "markdown-branch-push": "Markdown Branch Push",
    "markdown-branch-commit": "Markdown Branch Commit",
    "captured-turn": "Captured turn",
    "Markdown Branch Push": "Markdown Branch Push",
    "Markdown Branch Commit": "Markdown Branch Commit",
    "Captured turn": "Captured turn",
  };
  return known[cleaned] ?? known[skill] ?? cleaned;
}

function statusLabel(status: MarkdownWorkflowStepStatus): string {
  if (status === "completed") return "Completed";
  if (status === "skipped") return "Skipped";
  if (status === "blocked") return "Blocked";
  if (status === "pending") return "Pending";
  return "Unknown";
}

function statusRailClass(status: MarkdownWorkflowStepStatus): string {
  if (status === "completed") return "bg-emerald-500/20 text-emerald-200";
  if (status === "skipped") return "bg-slate-700/70 text-slate-300";
  if (status === "blocked") return "bg-rose-500/20 text-rose-200";
  if (status === "pending") return "bg-amber-500/20 text-amber-200";
  return "bg-slate-800 text-slate-500";
}

function runStatusLabel(status: MarkdownWorkflowRun["status"]): string {
  if (status === "completed") return "Completed";
  if (status === "blocked") return "Blocked";
  return "In progress";
}

function runStatusClass(status: MarkdownWorkflowRun["status"]): string {
  if (status === "completed") return "bg-emerald-500/15 text-emerald-200";
  if (status === "blocked") return "bg-rose-500/15 text-rose-200";
  return "bg-amber-500/15 text-amber-200";
}

function phaseLabel(phase: ChangeGroup["phase"]): string {
  if (phase === "review") return "Review";
  if (phase === "review_fix") return "Review fix";
  if (phase === "verification") return "Verification";
  if (phase === "planning") return "Planning";
  return "Implementation";
}

function latestGroup(session: ChangeSessionResponse | null): ChangeGroup | null {
  if (!session || session.groups.length === 0) return null;
  return session.groups[session.groups.length - 1];
}

function errorMessage(err: unknown): string {
  return (
    (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
    (err as Error)?.message ??
    "Unknown error"
  );
}

function shortSessionLabel(sessionId: string): string {
  if (!sessionId) return "";
  return sessionId.length > 12 ? sessionId.slice(0, 8) : sessionId;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value));
}

function formatTokens(value: number): string {
  if (value >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (value >= 1_000) return `${(value / 1_000).toFixed(1)}K`;
  return String(value);
}

function usageDetail(usage: CodexUsageResponse["all_time"]): string {
  return `Input ${formatTokens(usage.input_tokens)} · Output ${formatTokens(usage.output_tokens)} · Reasoning ${formatTokens(usage.reasoning_output_tokens)}`;
}

function formatLimitInline(limits: CodexRateLimits): string {
  const primary = formatPercent(limits.primary?.used_percent);
  const secondary = formatPercent(limits.secondary?.used_percent);
  return `${primary}/${secondary}`;
}

function formatPercent(value: number | null | undefined): string {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  return `${value.toFixed(value >= 10 ? 0 : 1)}%`;
}

function formatWindow(minutes: number | null | undefined): string {
  if (!minutes) return "window";
  if (minutes % 10080 === 0) return `${minutes / 10080}w`;
  if (minutes % 1440 === 0) return `${minutes / 1440}d`;
  if (minutes % 60 === 0) return `${minutes / 60}h`;
  return `${minutes}m`;
}

function formatReset(epochSeconds: number | null | undefined): string {
  if (!epochSeconds) return "-";
  return new Date(epochSeconds * 1000).toLocaleString("en-US", {
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
