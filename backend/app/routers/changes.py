from __future__ import annotations

import os
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.changes.default_docs import fill_default_docs
from app.services.changes.git_diff import collect_diff, resolve_project_root
from app.services.changes.graph_builder import ChangeGraph, build_graph
from app.services.changes.response_mapper import attach_response
from app.services.changes.session_delta import (
    filter_graph_to_session_delta,
    serialized_graph_snapshot,
)
from app.services.codex_usage import codex_usage_summary
from app.services.sessions.store import (
    append_group,
    append_workflow_event,
    default_session_id,
    get_latest_full_graph,
    get_latest_session,
    get_latest_workflow_full_graph,
)
from app.services.text_sanitizer import clean_captured_text

router = APIRouter()
DIFF_EVENT_STEP_KINDS = {"implementation", "review_fix"}


_CACHE_LOCK = threading.Lock()
_LATEST_RESULTS: dict[str, dict] = {}


class ChangesRequest(BaseModel):
    project_root: Optional[str] = Field(
        default=None,
        description="Git repository path. Defaults to CODEFLOW_PROJECT_ROOT or the server working directory.",
    )
    source: str = Field(default="working", description="working | staged | range | branch")
    base_ref: Optional[str] = None
    head_ref: Optional[str] = None
    assistant_response: str = Field(
        default="",
        description=(
            "Response text produced by Codex or Claude Code. When empty, each node and edge "
            "uses only documentation generated from the diff."
        ),
    )


class SessionCaptureRequest(ChangesRequest):
    user_prompt: str = Field(
        default="",
        description="Original user prompt, displayed in group documentation on the session timeline.",
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Identifier grouping events from the same Codex or Claude conversation. Defaults to repository and branch.",
    )


class SessionWorkflowEventRequest(SessionCaptureRequest):
    workflow_id: str = Field(
        default="",
        description="Stable ID for one Markdown review-loop command.",
    )
    run_id: str = Field(
        default="",
        description="ID for one Markdown file within a workflow.",
    )
    skill: str = Field(default="", description="markdown-branch-push or markdown-branch-commit")
    skill_label: str = Field(default="", description="Skill name displayed in the UI")
    command_label: str = Field(default="", description="Markdown command or run name displayed in the UI")
    markdown_path: str = Field(default="", description="Path to the Markdown implementation unit")
    markdown_title: str = Field(default="", description="Title of the Markdown implementation unit")
    markdown_content: str = Field(default="", description="Full Markdown implementation unit content")
    branch_name: str = Field(default="", description="Work branch for the Markdown implementation unit")
    step_id: str = Field(default="", description="Stable ID used to update the same step")
    step_kind: str = Field(
        default="implementation",
        description="preflight | markdown | branch | implementation | review | review_fix | verification | commit | push | merge",
    )
    step_label: str = Field(default="", description="Node title")
    step_summary: str = Field(default="", description="Summary displayed at the top of the node")
    step_detail: str = Field(default="", description="Description displayed in the node details panel")
    step_status: str = Field(default="completed", description="completed | skipped | pending | blocked | unknown")
    agent: str = Field(
        default="",
        description="Tool or agent that performed the step, such as claude-code or codex. Distinguishes implementation and review actors.",
    )
    agent_label: str = Field(default="", description="Agent name displayed in the UI")
    files: list[str] = Field(default_factory=list, description="Files directly associated with the step")


def _resolve_project_root(raw: Optional[str]) -> str:
    if raw and raw.strip():
        return raw.strip()
    env_root = os.getenv("CODEFLOW_PROJECT_ROOT", "").strip()
    if env_root:
        return env_root
    return str(Path.cwd())


def _resolve_lookup_project_root(raw: Optional[str]) -> str | None:
    if raw is None:
        return None
    resolved = _resolve_project_root(raw)
    try:
        return resolve_project_root(resolved)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _resolve_latest_project_root(raw: Optional[str]) -> str:
    project_root = _resolve_project_root(raw)
    try:
        return resolve_project_root(project_root)
    except ValueError:
        return project_root


def _cache_latest_result(result: dict) -> None:
    project_root = str(result.get("project_root") or "").strip()
    if not project_root:
        return
    _LATEST_RESULTS[project_root] = result


def _build_graph(request: ChangesRequest) -> ChangeGraph:
    project_root = _resolve_project_root(request.project_root)
    try:
        diff = collect_diff(
            project_root=project_root,
            source=request.source,  # type: ignore[arg-type]
            base_ref=request.base_ref,
            head_ref=request.head_ref,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    return build_graph(diff)


def _graph_response(graph: ChangeGraph, assistant_response: str) -> dict:
    cleaned_response = clean_captured_text(assistant_response)
    fill_default_docs(graph)
    if cleaned_response.strip():
        attach_response(graph, cleaned_response)

    return {
        "project_root": graph.project_root,
        "source": graph.source,
        "base_ref": graph.base_ref,
        "head_ref": graph.head_ref,
        "narrative": graph.narrative,
        "warnings": graph.warnings,
        "nodes": [asdict(n) for n in graph.nodes],
        "edges": [asdict(e) for e in graph.edges],
        "assistant_response": cleaned_response,
    }


def _run_analysis(request: ChangesRequest) -> dict:
    return _graph_response(_build_graph(request), request.assistant_response)


@router.post("/changes", tags=["Changes"])
async def changes_endpoint(request: ChangesRequest) -> dict:
    result = _run_analysis(request)
    with _CACHE_LOCK:
        _cache_latest_result(result)
    return result


@router.get("/changes/latest", tags=["Changes"])
async def changes_latest(project_root: Optional[str] = None) -> dict:
    """Return the most recent /api/changes result.

    If nothing is cached yet (e.g. fresh boot), run an analysis with the default
    project_root and an empty assistant_response so the UI is never blank.
    """
    resolved_root = _resolve_latest_project_root(project_root)
    with _CACHE_LOCK:
        cached = _LATEST_RESULTS.get(resolved_root)
    if cached is not None:
        return cached
    fallback = ChangesRequest(project_root=resolved_root, source="branch", assistant_response="")
    try:
        result = _run_analysis(fallback)
    except HTTPException as exc:
        return {
            "project_root": resolved_root,
            "source": "branch",
            "base_ref": None,
            "head_ref": None,
            "narrative": "",
            "warnings": [f"latest fallback failed: {exc.detail}"],
            "nodes": [],
            "edges": [],
            "assistant_response": "",
        }
    with _CACHE_LOCK:
        _cache_latest_result(result)
    return result


@router.post("/sessions/capture", tags=["Sessions"])
async def sessions_capture(request: SessionCaptureRequest) -> dict:
    """Create one chronological group from a user prompt + assistant response."""
    cleaned_response = clean_captured_text(request.assistant_response)
    full_graph = _build_graph(request)
    full_snapshot = serialized_graph_snapshot(full_graph)
    capture_session_id = (request.session_id or "").strip() or default_session_id(
        full_graph.project_root
    )
    previous_full_graph = get_latest_full_graph(full_graph.project_root, capture_session_id)

    filter_graph_to_session_delta(full_graph, previous_full_graph, cleaned_response)
    result = _graph_response(full_graph, cleaned_response)
    latest_result = _graph_response(_build_graph(request), cleaned_response)

    with _CACHE_LOCK:
        _cache_latest_result(latest_result)
    return append_group(
        project_root=result["project_root"],
        graph=result,
        full_graph=full_snapshot,
        user_prompt=request.user_prompt,
        session_id=capture_session_id,
    )


@router.post("/sessions/event", tags=["Sessions"])
async def sessions_event(request: SessionWorkflowEventRequest) -> dict:
    """Append one live Markdown review-loop step to the current session."""
    cleaned_response = clean_captured_text(request.assistant_response)
    full_graph = _build_graph(request)
    full_snapshot = serialized_graph_snapshot(full_graph)
    capture_session_id = (request.session_id or "").strip() or default_session_id(
        full_graph.project_root
    )
    previous_full_graph = get_latest_workflow_full_graph(
        full_graph.project_root,
        session_id=capture_session_id,
        workflow_id=request.workflow_id,
        run_id=request.run_id,
        markdown_path=request.markdown_path,
        markdown_title=request.markdown_title,
    )

    filter_graph_to_session_delta(full_graph, previous_full_graph, cleaned_response)
    result = _graph_response(full_graph, cleaned_response or request.step_detail or request.step_summary)
    latest_result = _graph_response(_build_graph(request), cleaned_response)

    with _CACHE_LOCK:
        _cache_latest_result(latest_result)
    return append_workflow_event(
        project_root=result["project_root"],
        graph=result,
        full_graph=full_snapshot,
        user_prompt=request.user_prompt,
        session_id=capture_session_id,
        workflow_id=request.workflow_id,
        run_id=request.run_id,
        skill=request.skill,
        skill_label=request.skill_label,
        command_label=request.command_label,
        markdown_path=request.markdown_path,
        markdown_title=request.markdown_title,
        markdown_content=request.markdown_content,
        branch_name=request.branch_name,
        step_id=request.step_id,
        step_kind=request.step_kind,
        step_label=request.step_label,
        step_summary=request.step_summary,
        step_detail=clean_captured_text(request.step_detail),
        step_status=request.step_status,
        agent=request.agent,
        agent_label=request.agent_label,
        files=_event_files_scope(request.step_kind, request.files),
    )


def _event_files_scope(step_kind: str, files: list[str]) -> list[str] | None:
    cleaned = [file.strip() for file in files if file.strip()]
    if cleaned:
        return cleaned
    if step_kind.strip().lower() in DIFF_EVENT_STEP_KINDS:
        return None
    return []


@router.get("/sessions/latest", tags=["Sessions"])
async def sessions_latest(
    project_root: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    resolved_root = _resolve_lookup_project_root(project_root)
    return get_latest_session(resolved_root, session_id)


@router.get("/changes/health", tags=["Changes"])
async def changes_health() -> dict:
    return {"status": "ok"}


@router.get("/codex/usage", tags=["Codex"])
async def codex_usage(project_root: Optional[str] = None) -> dict:
    resolved_root = _resolve_project_root(project_root) if project_root else None
    return codex_usage_summary(resolved_root)
