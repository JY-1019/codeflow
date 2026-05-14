from __future__ import annotations

from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.changes.git_diff import collect_diff
from app.services.changes.graph_builder import build_graph
from app.services.changes.response_mapper import attach_response

router = APIRouter()


class ChangesRequest(BaseModel):
    project_root: str
    source: str = Field(default="working", description="working | staged | range")
    base_ref: Optional[str] = None
    head_ref: Optional[str] = None
    assistant_response: str = Field(
        default="",
        description=(
            "Codex / Claude Code가 만든 응답 텍스트(설명/요약). 비워두면 "
            "그래프만 반환하고 노드/엣지 doc은 비어있게 됩니다."
        ),
    )


@router.post("/changes", tags=["Changes"])
async def changes_endpoint(request: ChangesRequest) -> dict:
    try:
        diff = collect_diff(
            project_root=request.project_root,
            source=request.source,  # type: ignore[arg-type]
            base_ref=request.base_ref,
            head_ref=request.head_ref,
        )
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    graph = build_graph(diff)
    attach_response(graph, request.assistant_response)

    return {
        "project_root": graph.project_root,
        "source": graph.source,
        "base_ref": graph.base_ref,
        "head_ref": graph.head_ref,
        "narrative": graph.narrative,
        "warnings": graph.warnings,
        "nodes": [asdict(n) for n in graph.nodes],
        "edges": [asdict(e) for e in graph.edges],
    }


@router.get("/changes/health", tags=["Changes"])
async def changes_health() -> dict:
    return {"status": "ok"}
