import ReactMarkdown from "react-markdown";
import rehypeHighlight from "rehype-highlight";
import { useEffect, useState, type ReactNode } from "react";
import {
  Bot,
  ChevronDown,
  CheckCircle2,
  CircleDashed,
  FileText,
  GitBranch,
  GitCompareArrows,
  Link2,
  MessageSquareText,
  Route,
  SearchCheck,
  ShieldCheck,
  SkipForward,
  Sparkles,
  XCircle,
} from "lucide-react";
import { agentDisplayLabel } from "@/flow/utils/agentLabel";
import type {
  ChangeEdge,
  ChangeGraphResponse,
  ChangeGroup,
  ChangeNode,
  MarkdownWorkflowRun,
  MarkdownWorkflowStep,
  MarkdownWorkflowStepStatus,
  TechnicalConsideration,
} from "@/types/changes";

interface DocPanelProps {
  graph: ChangeGraphResponse | null;
  selectedNodeId: string | null;
  selectedEdgeId: string | null;
  selectedWorkflowStep?: SelectedWorkflowStepDetails | null;
  selectedGroup?: ChangeGroup | null;
}

interface SelectedWorkflowStepDetails {
  group: ChangeGroup;
  run: MarkdownWorkflowRun | null;
  step: MarkdownWorkflowStep;
  nodeId: string;
}

export function DocPanel({
  graph,
  selectedNodeId,
  selectedEdgeId,
  selectedWorkflowStep,
  selectedGroup,
}: DocPanelProps) {
  if (selectedWorkflowStep) {
    return <WorkflowStepDoc item={selectedWorkflowStep} />;
  }

  if (selectedGroup) {
    return <GroupDoc group={selectedGroup} />;
  }

  if (!graph) {
    return (
      <div className="flex h-full min-h-0 min-w-0 items-center justify-center overflow-hidden px-4 text-center text-[12px] text-slate-500">
        Load a session or diff to see its summary here.
      </div>
    );
  }

  const node = selectedNodeId ? graph.nodes.find((n) => n.id === selectedNodeId) : null;
  const edge = selectedEdgeId ? graph.edges.find((e) => e.id === selectedEdgeId) : null;

  if (node) return <NodeDoc node={node} />;
  if (edge) return <EdgeDoc edge={edge} graph={graph} />;
  return <GraphDoc graph={graph} />;
}

function GroupDoc({ group }: { group: ChangeGroup }) {
  const summary = group.summary;
  const implementation = summary?.implementation ?? [];
  const review = summary?.review ?? [];
  const considerations = summary?.technical_considerations ?? [];
  const fileNodes = changedFileNodes(group.graph);
  const files = fileNodes.length > 0 ? fileNodes.map((node) => node.file) : summary?.changed_files ?? [];
  const workflowRuns = group.workflow_runs ?? [];
  const workflowFlowStepCount = workflowRuns.reduce((total, run) => total + run.steps.length, 0);
  const workflowSteps = workflowRuns
    .flatMap((run) => run.steps)
    .filter((step) => ["implementation", "review", "review_fix", "verification"].includes(step.kind));

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-y-auto p-3 text-[13px]">
      <div className="flex items-center justify-between gap-2">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">
            Step {group.sequence ?? ""}
          </div>
          <div className="mt-0.5 text-base font-semibold text-slate-100">
            {group.phase_label ?? "Implementation"} · {group.name}
          </div>
        </div>
        <span className="rounded bg-slate-800 px-2 py-1 text-[10px] uppercase tracking-wider text-slate-300">
          {group.phase ?? "implementation"}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] text-slate-300">
        <Stat label="Files" value={summary?.file_count ?? group.graph.nodes.length} />
        <Stat label="Steps" value={workflowFlowStepCount || summary?.workflow_step_count || 1} />
        <Stat label="Added" value={`+${summary?.added_lines ?? 0}`} tone="emerald" />
        <Stat label="Removed" value={`-${summary?.removed_lines ?? 0}`} tone="rose" />
      </div>

      <Section icon={MessageSquareText} title="User prompt">
        <MarkdownBlock>
          {group.user_prompt || "_No user prompt was recorded._"}
        </MarkdownBlock>
      </Section>

      <Section icon={Sparkles} title="Group activity">
        <GroupNarrative
          implementation={implementation}
          review={review}
          workflowSteps={workflowSteps}
        />
      </Section>

      {workflowRuns.length > 0 ? (
        <Section icon={SearchCheck} title="Review loop status">
          <WorkflowRunList runs={workflowRuns} />
        </Section>
      ) : null}

      <Considerations items={considerations} />

      <Section icon={FileText} title="Changed files">
        <FileDiffList fileNodes={fileNodes} fallbackFiles={files} />
      </Section>
    </div>
  );
}

function WorkflowStepDoc({ item }: { item: SelectedWorkflowStepDetails }) {
  const { group, run, step } = item;
  const stepGraph = step.graph ?? group.graph;
  const allFileNodes = changedFileNodes(stepGraph);
  const showsDiff = step.kind === "implementation" || step.kind === "review_fix";
  const fileNodes = showsDiff ? allFileNodes : [];
  const fallbackFiles = showsDiff
    ? step.files.length > 0
      ? step.files
      : group.summary?.changed_files ?? allFileNodes.map((node) => node.file)
    : [];
  const added = showsDiff ? sum(allFileNodes.map((node) => node.added_lines)) : 0;
  const removed = showsDiff ? sum(allFileNodes.map((node) => node.removed_lines)) : 0;
  const StatusIcon = statusIcon(step.status);
  const content = stepPrimaryContent(item);
  const agentLabel = agentDisplayLabel(step.agent, step.agent_label);

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-y-auto p-3 text-[13px]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[10px] uppercase tracking-wider text-slate-500">
            {stepKindLabel(step.kind)} node
          </div>
          <div className="mt-0.5 text-base font-semibold leading-snug text-slate-100">
            {step.label}
          </div>
          <div className="mt-1 text-[12px] leading-relaxed text-slate-400">
            Group {group.sequence ?? ""} · {group.name}
            {run ? ` · ${workflowSkillLabel(run.skill, run.skill_label)}` : ""}
            {agentLabel ? ` · ${agentLabel}` : ""}
          </div>
        </div>
        <span className={`inline-flex shrink-0 items-center gap-1 rounded px-2 py-1 text-[10px] ${statusClass(step.status)}`}>
          <StatusIcon className="h-3 w-3" />
          {statusLabel(step.status)}
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] text-slate-300">
        <Stat label="Node" value={stepKindLabel(step.kind)} />
        <Stat label="Status" value={statusLabel(step.status)} />
        {showsDiff ? (
          <>
            <Stat label="Added" value={`+${added}`} tone="emerald" />
            <Stat label="Removed" value={`-${removed}`} tone="rose" />
          </>
        ) : (
          <>
            <Stat label="Files" value="-" />
            <Stat label="Diff" value="None" />
          </>
        )}
      </div>

      <Section icon={stepSectionIcon(step.kind)} title={stepPrimaryTitle(step.kind)}>
        <MarkdownBlock>
          {content || "_No summary was recorded for this node._"}
        </MarkdownBlock>
      </Section>

      {showsDiff ? (
        <Section icon={GitCompareArrows} title="Full diff">
          <FileDiffList fileNodes={fileNodes} fallbackFiles={fallbackFiles} />
        </Section>
      ) : null}
    </div>
  );
}

function GroupNarrative({
  implementation,
  review,
  workflowSteps,
}: {
  implementation: string[];
  review: string[];
  workflowSteps: MarkdownWorkflowStep[];
}) {
  const groupedSteps = groupWorkflowSteps(workflowSteps);
  const hasStructuredSteps = Object.values(groupedSteps).some((items) => items.length > 0);
  const implementationStepItems = groupedSteps.implementation.map((step) => step.summary);
  const reviewStepItems = groupedSteps.review.map((step) => step.summary);
  const reviewFixItems = groupedSteps.review_fix.map((step) => step.summary);
  const verificationItems = groupedSteps.verification.map((step) => step.summary);

  if (!hasStructuredSteps) {
    return (
      <div className="space-y-3">
        <NarrativeBlock title="Implementation activity" items={implementation} empty="No implementation details yet." />
        <NarrativeBlock title="Review or verification activity" items={review} empty="No review or verification details yet." />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <NarrativeBlock
        title="Implementation"
        items={[
          ...withoutExactText(implementation, reviewFixItems),
          ...implementationStepItems,
        ]}
        empty="No implementation details yet."
      />
      <NarrativeBlock
        title="Review"
        items={[
          ...withoutExactText(review, verificationItems),
          ...reviewStepItems,
        ]}
        empty="No review details yet."
      />
      <NarrativeBlock
        title="Review fixes"
        items={reviewFixItems}
        empty="No review findings needed fixing, or none have been recorded yet."
      />
      <NarrativeBlock
        title="Verification"
        items={verificationItems}
        empty="No verification details yet."
      />
    </div>
  );
}

function NarrativeBlock({
  title,
  items,
  empty,
}: {
  title: string;
  items: string[];
  empty: string;
}) {
  const uniqueItems = uniqueText(items).slice(0, 4);
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/45 px-3 py-2">
      <div className="mb-1 text-[12px] font-semibold text-slate-100">{title}</div>
      {uniqueItems.length > 0 ? (
        <div className="space-y-1.5 text-[12px] leading-relaxed text-slate-300">
          {uniqueItems.map((item, index) => (
            <p key={`${title}-${index}-${item}`}>{item}</p>
          ))}
        </div>
      ) : (
        <div className="text-[12px] text-slate-500">{empty}</div>
      )}
    </div>
  );
}

function WorkflowRunList({ runs }: { runs: MarkdownWorkflowRun[] }) {
  return (
    <div className="space-y-3">
      {runs.map((run) => (
        <div key={run.id} className="rounded-md border border-slate-800 bg-slate-950/45">
          <div className="border-b border-slate-800 bg-slate-900/70 px-3 py-2">
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="inline-flex items-center gap-1.5 rounded bg-sky-500/15 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-sky-200">
                  <Route className="h-3 w-3" />
                  {workflowSkillLabel(run.skill, run.skill_label)}
                </div>
                <div className="mt-1 truncate text-[12px] font-semibold text-slate-100" title={run.command_label}>
                  {run.command_label}
                </div>
              </div>
              <span className="shrink-0 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-slate-300">
                {run.status === "completed" ? "Completed" : run.status === "blocked" ? "Blocked" : "In progress"}
              </span>
            </div>
            {run.markdown_path || run.branch_name ? (
              <div className="mt-2 space-y-1 text-[11px] text-slate-500">
                {run.markdown_path ? (
                  <div className="truncate font-mono" title={run.markdown_path}>
                    {run.markdown_path}
                  </div>
                ) : null}
                {run.branch_name ? (
                  <div className="flex items-center gap-1.5">
                    <GitBranch className="h-3 w-3" />
                    <span className="truncate font-mono" title={run.branch_name}>{run.branch_name}</span>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
          <div className="space-y-3 p-3">
            <WorkflowStepList steps={run.steps} />
          </div>
        </div>
      ))}
    </div>
  );
}

function WorkflowStepList({ steps }: { steps: MarkdownWorkflowStep[] }) {
  return (
    <ol className="space-y-2">
      {steps.map((step, index) => {
        const StatusIcon = statusIcon(step.status);
        const agentLabel = agentDisplayLabel(step.agent, step.agent_label);
        return (
          <li key={step.id} className="rounded-md border border-slate-800 bg-slate-900/45 px-3 py-2">
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <span className="text-[12px] font-semibold text-slate-100">{step.label}</span>
                  {agentLabel ? (
                    <span
                      className="inline-flex items-center gap-1 rounded bg-slate-800 px-1.5 py-0.5 text-[10px] text-slate-300"
                      title={`Agent: ${agentLabel}`}
                    >
                      <Bot className="h-3 w-3" />
                      <span className="max-w-[96px] truncate">{agentLabel}</span>
                    </span>
                  ) : null}
                </div>
                <div className="mt-1 text-[12px] leading-relaxed text-slate-400">
                  {step.summary}
                </div>
              </div>
              <span className={`inline-flex shrink-0 items-center gap-1 rounded px-1.5 py-0.5 text-[10px] ${statusClass(step.status)}`}>
                <StatusIcon className="h-3 w-3" />
                {statusLabel(step.status)}
              </span>
            </div>
            {step.files.length > 0 ? (
              <div className="mt-2 flex flex-wrap gap-1">
                {step.files.map((file) => (
                  <span
                    key={file}
                    className="max-w-full truncate rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-300"
                    title={file}
                  >
                    {file}
                  </span>
                ))}
              </div>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

function stepPrimaryContent({ run, step }: SelectedWorkflowStepDetails): string {
  const parts = [step.summary, step.detail].map((item) => item.trim()).filter(Boolean);
  if (step.kind === "markdown") {
    const markdownContent = run?.markdown_content?.trim() ?? "";
    if (markdownContent) {
      parts.push(markdownContent);
    } else if (run?.markdown_path) {
      parts.push(`Markdown file: \`${run.markdown_path}\``);
    }
  }
  return uniqueText(parts).join("\n\n");
}

function stepPrimaryTitle(kind: MarkdownWorkflowStep["kind"]): string {
  if (kind === "preflight") return "Preflight details";
  if (kind === "markdown") return "Markdown command";
  if (kind === "branch") return "Branch setup";
  if (kind === "implementation") return "Implementation summary";
  if (kind === "review") return "Review summary";
  if (kind === "review_fix") return "Review fix summary";
  if (kind === "verification") return "Verification result";
  if (kind === "commit") return "Commit result";
  if (kind === "push") return "Push result";
  if (kind === "merge") return "Merge result";
  return "Node summary";
}

function stepKindLabel(kind: MarkdownWorkflowStep["kind"]): string {
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

function stepSectionIcon(kind: MarkdownWorkflowStep["kind"]) {
  if (kind === "review" || kind === "review_fix") return SearchCheck;
  if (kind === "verification") return ShieldCheck;
  if (kind === "markdown") return FileText;
  return Sparkles;
}

function GraphDoc({ graph }: { graph: ChangeGraphResponse }) {
  const files = changedFileNodes(graph);
  const added = sum(files.map((node) => node.added_lines));
  const removed = sum(files.map((node) => node.removed_lines));

  return (
    <div className="h-full min-h-0 min-w-0 space-y-4 overflow-y-auto p-3 text-[13px]">
      <div>
        <div className="text-[10px] uppercase tracking-wider text-slate-500">Diff summary</div>
        <div className="mt-0.5 text-base font-semibold text-slate-100">
          {files.length} file{files.length === 1 ? "" : "s"} · +{added}/-{removed}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2 text-[12px] text-slate-300">
        <Stat label="Nodes" value={graph.nodes.length} />
        <Stat label="Relations" value={graph.edges.length} />
        <Stat label="Changed files" value={files.length} />
        <Stat label="Affected files" value={graph.nodes.filter((n) => n.kind === "affected").length} />
      </div>

      <Section icon={GitCompareArrows} title="Implementation scope">
        {files.length > 0 ? (
          <FileDiffList fileNodes={files} fallbackFiles={files.map((node) => node.file)} />
        ) : (
          <EmptyLine text="No files were changed directly in the selected diff." />
        )}
      </Section>

      {graph.warnings.length > 0 ? (
        <div className="rounded border border-amber-700/60 bg-amber-950/40 p-2 text-[12px] text-amber-200">
          <div className="mb-1 font-semibold">Warnings</div>
          <ul className="list-disc pl-4">
            {graph.warnings.map((warning, index) => (
              <li key={index}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function NodeDoc({ node }: { node: ChangeNode }) {
  const hunkCount = countHunks(node.snippet);
  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col overflow-y-auto p-3 text-[13px]">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">File</div>
      <div className="mt-0.5 text-base font-semibold text-slate-100">{node.label}</div>
      <div className="truncate text-[12px] text-slate-400" title={node.file}>
        {node.file}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 text-[12px] text-slate-300">
        <Stat label="Status" value={changeStatusLabel(node.status)} />
        <Stat label="Hunks" value={hunkCount || "-"} />
        <Stat label="Added" value={`+${node.added_lines}`} tone="emerald" />
        <Stat label="Removed" value={`-${node.removed_lines}`} tone="rose" />
      </div>

      <Section icon={Sparkles} title="Role summary">
        <MarkdownBlock>
          {node.body || node.summary || "_No summary is available for this file yet._"}
        </MarkdownBlock>
      </Section>

      <Section icon={GitCompareArrows} title="Removed/added lines">
        <RawDiffBlock snippet={node.snippet} />
      </Section>
    </div>
  );
}

function EdgeDoc({ edge, graph }: { edge: ChangeEdge; graph: ChangeGraphResponse }) {
  const sourceNode = graph.nodes.find((n) => n.id === edge.source);
  const targetNode = graph.nodes.find((n) => n.id === edge.target);
  return (
    <div className="flex h-full min-h-0 flex-col overflow-y-auto p-3 text-[13px]">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">Relationship</div>
      <div className="mt-0.5 text-base font-semibold text-slate-100">
        {edge.kind} · {edge.label || "Connection"}
      </div>
      <div className="mt-1 text-[12px] text-slate-400">
        {sourceNode?.file ?? edge.source}
        <span className="mx-1 text-slate-600">→</span>
        {targetNode?.file ?? edge.target}
      </div>

      <Section icon={Link2} title="Connection details">
        <MarkdownBlock>
          {edge.body || edge.summary || "_No relationship summary is available yet._"}
        </MarkdownBlock>
      </Section>
    </div>
  );
}

function Section({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof FileText;
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="mt-4">
      <div className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-slate-500">
        <Icon className="h-3.5 w-3.5 text-cyan-300" />
        {title}
      </div>
      {children}
    </section>
  );
}

function Considerations({ items }: { items: TechnicalConsideration[] }) {
  if (items.length === 0) return null;
  return (
    <Section icon={ShieldCheck} title="Technical considerations">
      <div className="space-y-2">
        {items.map((item) => (
          <div key={item.label} className="rounded-md border border-slate-800 bg-slate-950/45 px-3 py-2">
            <div className="text-[12px] font-semibold text-slate-100">{item.label}</div>
            <div className="mt-1 text-[12px] leading-relaxed text-slate-400">{item.detail}</div>
          </div>
        ))}
      </div>
    </Section>
  );
}

function FileDiffList({
  fileNodes,
  fallbackFiles,
}: {
  fileNodes: ChangeNode[];
  fallbackFiles: string[];
}) {
  const fileKey = fileNodes.map((node) => node.id).join("\n");
  const [openFileIds, setOpenFileIds] = useState<Set<string>>(
    () => new Set(fileNodes.slice(0, 8).map((node) => node.id))
  );

  useEffect(() => {
    setOpenFileIds(new Set(fileNodes.slice(0, 8).map((node) => node.id)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileKey]);

  if (fileNodes.length === 0) {
    return fallbackFiles.length > 0 ? (
      <ul className="space-y-1.5 text-[12px] text-slate-300">
        {fallbackFiles.map((file) => (
          <li key={file} className="truncate rounded border border-slate-800 bg-slate-950/45 px-2 py-1.5">
            {file}
          </li>
        ))}
      </ul>
    ) : (
      <EmptyLine text="No file diff is associated with this step." />
    );
  }

  return (
    <div className="space-y-3">
      {fileNodes.map((node) => {
        const isOpen = openFileIds.has(node.id);
        const hunkCount = countHunks(node.snippet) || 1;
        return (
          <details
            key={node.id}
            open={isOpen}
            onToggle={(event) => {
              const nextOpen = event.currentTarget.open;
              setOpenFileIds((current) => {
                const next = new Set(current);
                if (nextOpen) next.add(node.id);
                else next.delete(node.id);
                return next;
              });
            }}
            className="group rounded-md border border-slate-800 bg-slate-950/45 shadow-sm"
          >
            <summary className="flex cursor-pointer select-none list-none items-center gap-2 rounded-t-md border-b border-slate-800 bg-slate-900/70 px-3 py-2 [&::-webkit-details-marker]:hidden">
              <ChevronDown className="h-3.5 w-3.5 shrink-0 text-slate-500 transition-transform group-open:rotate-0 -rotate-90" />
              <div className="min-w-0 flex-1">
                <div className="truncate font-mono text-[12px] font-semibold text-slate-100" title={node.file}>
                  {node.file}
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-[10px] uppercase tracking-wide text-slate-500">
                  <span>{changeStatusLabel(node.status)}</span>
                  <span>{hunkCount} hunk{hunkCount === 1 ? "" : "s"}</span>
                </div>
              </div>
              <span className="shrink-0 rounded bg-emerald-950/45 px-1.5 py-0.5 font-mono text-[11px] text-emerald-200">
                +{node.added_lines}
              </span>
              <span className="shrink-0 rounded bg-rose-950/45 px-1.5 py-0.5 font-mono text-[11px] text-rose-200">
                -{node.removed_lines}
              </span>
            </summary>
            {isOpen ? (
              <div>
                <RawDiffBlock snippet={node.snippet} compact />
              </div>
            ) : null}
          </details>
        );
      })}
    </div>
  );
}

function RawDiffBlock({ snippet, compact = false }: { snippet: string; compact?: boolean }) {
  const lines = diffDisplayLines(snippet);
  if (lines.length === 0) {
    return <EmptyLine text="No removed or added lines to display." />;
  }

  return (
    <div className={`${compact ? "" : "rounded-md border border-slate-800"} max-w-full overflow-x-auto bg-slate-950`}>
      <table className="w-max min-w-full border-collapse font-mono text-[11px] leading-5">
        <tbody>
          {lines.map((line, index) => (
            <tr
              key={`${index}-${line.raw}`}
              className={diffRowClass(line.kind)}
            >
              {line.kind === "hunk" ? (
                <td colSpan={4} className="px-3 py-1.5 text-sky-200">
                  {line.text}
                </td>
              ) : (
                <>
                  <td className={lineNumberClass(line.kind, "old")}>{line.oldLine ?? ""}</td>
                  <td className={lineNumberClass(line.kind, "new")}>{line.newLine ?? ""}</td>
                  <td className="w-7 select-none px-2 text-center text-slate-500">
                    {line.kind === "added" ? "+" : line.kind === "removed" ? "-" : ""}
                  </td>
                  <td className="min-w-[420px] whitespace-pre py-0.5 pr-4 align-top text-slate-200">
                    {line.text || " "}
                  </td>
                </>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

interface DiffDisplayLine {
  kind: "hunk" | "context" | "added" | "removed";
  oldLine: number | null;
  newLine: number | null;
  text: string;
  raw: string;
}

function diffDisplayLines(snippet: string): DiffDisplayLine[] {
  const rows: DiffDisplayLine[] = [];
  let oldLine = 0;
  let newLine = 0;

  for (const raw of snippet.split("\n")) {
    const hunk = parseHunkHeader(raw);
    if (hunk) {
      oldLine = hunk.oldStart;
      newLine = hunk.newStart;
      rows.push({ kind: "hunk", oldLine: null, newLine: null, text: raw, raw });
      continue;
    }

    if (raw.startsWith("+ ")) {
      rows.push({
        kind: "added",
        oldLine: null,
        newLine,
        text: raw.slice(2),
        raw,
      });
      newLine += 1;
      continue;
    }

    if (raw.startsWith("- ")) {
      rows.push({
        kind: "removed",
        oldLine,
        newLine: null,
        text: raw.slice(2),
        raw,
      });
      oldLine += 1;
      continue;
    }

    if (raw.startsWith("  ")) {
      rows.push({
        kind: "context",
        oldLine,
        newLine,
        text: raw.slice(2),
        raw,
      });
      oldLine += 1;
      newLine += 1;
    }
  }

  return rows;
}

function parseHunkHeader(raw: string): { oldStart: number; newStart: number } | null {
  const match = raw.match(/^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
  if (!match) return null;
  return {
    oldStart: Number(match[1]),
    newStart: Number(match[2]),
  };
}

function diffRowClass(kind: DiffDisplayLine["kind"]): string {
  if (kind === "hunk") return "border-y border-slate-800 bg-sky-950/25 text-sky-200";
  if (kind === "added") return "bg-emerald-950/35 text-emerald-50";
  if (kind === "removed") return "bg-rose-950/35 text-rose-50";
  return "bg-slate-950 text-slate-300";
}

function lineNumberClass(kind: DiffDisplayLine["kind"], side: "old" | "new"): string {
  const base = "w-11 select-none border-r px-2 text-right align-top text-slate-500";
  if (kind === "added" && side === "new") {
    return `${base} border-emerald-900/50 bg-emerald-950/50 text-emerald-300`;
  }
  if (kind === "removed" && side === "old") {
    return `${base} border-rose-900/50 bg-rose-950/50 text-rose-300`;
  }
  return `${base} border-slate-800 bg-slate-900/55`;
}

function MarkdownBlock({ children }: { children: string }) {
  return (
    <div className="markdown-body rounded-md border border-slate-800 bg-slate-950/45 px-3 py-2 text-slate-300">
      <ReactMarkdown rehypePlugins={[rehypeHighlight]}>{children}</ReactMarkdown>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
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
    <div className="rounded border border-slate-800 bg-slate-950/55 px-2.5 py-2">
      <div className="text-[10px] uppercase text-slate-500">{label}</div>
      <div className={`mt-1 text-base font-semibold ${valueClass}`}>{value}</div>
    </div>
  );
}

function EmptyLine({ text }: { text: string }) {
  return (
    <div className="rounded-md border border-slate-800 bg-slate-950/35 px-3 py-3 text-[12px] text-slate-500">
      {text}
    </div>
  );
}

function changedFileNodes(graph: ChangeGraphResponse): ChangeNode[] {
  return graph.nodes
    .filter((node) => node.kind === "changed" && node.symbol_kind === "file")
    .sort((a, b) => b.added_lines + b.removed_lines - (a.added_lines + a.removed_lines));
}

function countHunks(snippet: string): number {
  if (!snippet.trim()) return 0;
  return snippet.split("\n").filter((line) => line.startsWith("@@")).length || 1;
}

function changeStatusLabel(status: string): string {
  if (status === "added") return "Added";
  if (status === "modified") return "Modified";
  if (status === "deleted") return "Deleted";
  if (status === "renamed") return "Renamed";
  return status || "Changed";
}

function statusIcon(status: MarkdownWorkflowStepStatus) {
  if (status === "completed") return CheckCircle2;
  if (status === "skipped") return SkipForward;
  if (status === "blocked") return XCircle;
  return CircleDashed;
}

function statusLabel(status: MarkdownWorkflowStepStatus): string {
  if (status === "completed") return "Completed";
  if (status === "skipped") return "Skipped";
  if (status === "blocked") return "Blocked";
  if (status === "pending") return "Pending";
  return "Unknown";
}

function statusClass(status: MarkdownWorkflowStepStatus): string {
  if (status === "completed") return "bg-emerald-500/15 text-emerald-200";
  if (status === "skipped") return "bg-slate-700/60 text-slate-300";
  if (status === "blocked") return "bg-rose-500/15 text-rose-200";
  if (status === "pending") return "bg-amber-500/15 text-amber-200";
  return "bg-slate-800 text-slate-400";
}

function workflowSkillLabel(skill: string, label?: string): string {
  const cleaned = label?.trim() || skill.trim();
  const known: Record<string, string> = {
    "markdown-branch-push": "Markdown Branch Push",
    "markdown-branch-commit": "Markdown Branch Commit",
    "captured-turn": "Captured turn",
    "codeflow": "Codeflow capture",
    general: "General capture",
    "Markdown Branch Push": "Markdown Branch Push",
    "Markdown Branch Commit": "Markdown Branch Commit",
    "Captured turn": "Captured turn",
  };
  return known[cleaned] ?? known[skill] ?? cleaned;
}

function groupWorkflowSteps(steps: MarkdownWorkflowStep[]): Record<string, MarkdownWorkflowStep[]> {
  return {
    implementation: steps.filter((step) => step.kind === "implementation"),
    review: steps.filter((step) => step.kind === "review"),
    review_fix: steps.filter((step) => step.kind === "review_fix"),
    verification: steps.filter((step) => step.kind === "verification"),
  };
}

function uniqueText(items: string[]): string[] {
  const seen = new Set<string>();
  const output: string[] = [];
  for (const item of items) {
    const normalized = item.trim();
    if (!normalized || seen.has(normalized)) continue;
    seen.add(normalized);
    output.push(normalized);
  }
  return output;
}

function withoutExactText(items: string[], excludedItems: string[]): string[] {
  const excluded = new Set(excludedItems.map((item) => item.trim()).filter(Boolean));
  return items.filter((item) => !excluded.has(item.trim()));
}

function sum(values: number[]): number {
  return values.reduce((total, value) => total + value, 0);
}
