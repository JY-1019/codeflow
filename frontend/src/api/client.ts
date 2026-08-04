import axios from "axios";
import type {
  ChangeGraphResponse,
  ChangeSessionResponse,
  ChangeSource,
  CodexUsageResponse,
} from "@/types/changes";

const packagedRendererProtocols = new Set(["file:", "codeflow:"]);
const apiBaseURL = packagedRendererProtocols.has(window.location.protocol)
  ? "http://127.0.0.1:8019/api"
  : "/api";

const http = axios.create({
  baseURL: apiBaseURL,
  timeout: 60_000,
});

export interface FetchChangesParams {
  projectRoot: string;
  source?: ChangeSource;
  baseRef?: string;
  headRef?: string;
  assistantResponse?: string;
}

export async function fetchChanges(
  params: FetchChangesParams
): Promise<ChangeGraphResponse> {
  const res = await http.post<ChangeGraphResponse>("/changes", {
    project_root: params.projectRoot || undefined,
    source: params.source ?? "working",
    base_ref: params.baseRef,
    head_ref: params.headRef,
    assistant_response: params.assistantResponse ?? "",
  });
  return res.data;
}

export async function fetchLatestChanges(projectRoot?: string): Promise<ChangeGraphResponse> {
  const res = await http.get<ChangeGraphResponse>("/changes/latest", {
    params: projectRoot ? { project_root: projectRoot } : undefined,
  });
  return res.data;
}

export async function fetchLatestSession(
  projectRoot?: string,
  sessionId?: string
): Promise<ChangeSessionResponse> {
  const res = await http.get<ChangeSessionResponse>("/sessions/latest", {
    params: {
      project_root: projectRoot || undefined,
      session_id: sessionId || undefined,
    },
  });
  return res.data;
}

export async function fetchCodexUsage(projectRoot?: string): Promise<CodexUsageResponse> {
  const res = await http.get<CodexUsageResponse>("/codex/usage", {
    params: projectRoot ? { project_root: projectRoot } : undefined,
  });
  return res.data;
}
