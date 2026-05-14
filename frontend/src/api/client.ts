import axios from "axios";
import type { ChangeGraphResponse } from "@/types/changes";

const http = axios.create({
  baseURL: "/api",
  timeout: 60_000,
});

export interface FetchChangesParams {
  projectRoot: string;
  source?: "working" | "staged" | "range";
  baseRef?: string;
  headRef?: string;
  assistantResponse?: string;
}

export async function fetchChanges(
  params: FetchChangesParams
): Promise<ChangeGraphResponse> {
  const res = await http.post<ChangeGraphResponse>("/changes", {
    project_root: params.projectRoot,
    source: params.source ?? "working",
    base_ref: params.baseRef,
    head_ref: params.headRef,
    assistant_response: params.assistantResponse ?? "",
  });
  return res.data;
}
