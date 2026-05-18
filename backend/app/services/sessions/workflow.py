from __future__ import annotations

import re
from pathlib import Path
from typing import Any


MAX_WORKFLOW_RUNS = 12
MAX_MARKDOWN_CHARS = 12_000

WORKFLOW_SKILL_LABELS: dict[str, str] = {
    "markdown-branch-push": "Markdown Branch Push",
    "markdown-branch-commit": "Markdown Branch Commit",
}


def build_markdown_workflow_runs(
    *,
    prompt: str,
    response: str,
    graph: dict[str, Any],
) -> list[dict[str, Any]]:
    """Infer Markdown skill workflow runs from captured prompt/response text.

    Codeflow Light stays local and deterministic: skills can keep sending just
    prompt/response/diff, and this layer turns recognizable Markdown Branch
    Push/Commit captures into a structured flow. Future capture payloads can
    also include richer wording without changing the API contract.
    """
    combined = f"{prompt}\n{response}"
    skills = _detected_markdown_skills(prompt)
    units = _extract_markdown_units(prompt, response)

    if not skills:
        return []

    if not units:
        units = [_fallback_markdown_unit(prompt)]

    changed_files = _changed_files(graph)
    runs: list[dict[str, Any]] = []
    for skill in skills:
        for index, unit in enumerate(units[:MAX_WORKFLOW_RUNS]):
            run_id = f"{skill}:{_safe_id(unit.get('path') or unit.get('title') or str(index + 1))}:{index + 1}"
            steps = _workflow_steps(
                skill=skill,
                prompt=prompt,
                response=response,
                changed_files=changed_files,
                markdown_content=unit.get("content", ""),
                markdown_path=unit.get("path", ""),
            )
            runs.append(
                {
                    "id": run_id,
                    "skill": skill,
                    "skill_label": WORKFLOW_SKILL_LABELS.get(skill, skill),
                    "command_label": _command_label(skill, unit),
                    "markdown_path": unit.get("path", ""),
                    "markdown_title": unit.get("title", ""),
                    "markdown_content": _limit_text(unit.get("content", "")),
                    "branch_name": _branch_name(combined),
                    "status": _run_status(steps),
                    "steps": steps,
                }
            )
    return runs[:MAX_WORKFLOW_RUNS]


def _detected_markdown_skills(text: str) -> list[str]:
    lower = text.lower()
    skills: list[str] = []
    push_signal = _has_explicit_skill_invocation(lower, "markdown-branch-push")
    commit_signal = _has_explicit_skill_invocation(lower, "markdown-branch-commit")

    if push_signal:
        skills.append("markdown-branch-push")
    if commit_signal:
        skills.append("markdown-branch-commit")
    return skills


def _has_explicit_skill_invocation(lower_text: str, skill: str) -> bool:
    markers = [
        f"${skill}",
        f"/skills/{skill}/skill.md",
        f"\\skills\\{skill}\\skill.md",
        f"<skill>{skill}</skill>",
    ]
    return any(marker in lower_text for marker in markers)


def _extract_markdown_units(prompt: str, response: str) -> list[dict[str, str]]:
    units: list[dict[str, str]] = []
    seen: set[str] = set()

    for content in _fenced_markdown_blocks(prompt):
        key = _normalize_key(content)
        if key in seen:
            continue
        seen.add(key)
        units.append(
            {
                "path": "",
                "title": _markdown_title(content),
                "content": content.strip(),
            }
        )

    for path in _markdown_paths(f"{prompt}\n{response}"):
        key = _normalize_key(path)
        if key in seen:
            continue
        seen.add(key)
        units.append(
            {
                "path": path,
                "title": Path(path).name,
                "content": "",
            }
        )

    return units


def _fenced_markdown_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    for match in re.finditer(r"```(?:markdown|md)?\s*\n(?P<body>.*?)```", text, re.IGNORECASE | re.DOTALL):
        body = match.group("body").strip()
        if body:
            blocks.append(body)
    return blocks


def _markdown_paths(text: str) -> list[str]:
    output: list[str] = []
    pattern = re.compile(
        r"(?P<path>(?:~|/|\./|\../)?(?:[\w.$() -]+/)*[\w.$() -]+\.(?:md|markdown))",
        re.IGNORECASE,
    )
    for match in pattern.finditer(text):
        path = match.group("path").strip()
        name = Path(path).name.lower()
        if name == "skill.md":
            continue
        if "/node_modules/" in path or "/dist/" in path or "/build/" in path:
            continue
        output.append(path)
    return output


def _fallback_markdown_unit(prompt: str) -> dict[str, str]:
    content = _without_skill_reference_blocks(prompt).strip() or prompt.strip()
    title = _markdown_title(content) if content else "현재 요청"
    return {
        "path": "",
        "title": title or "현재 요청",
        "content": content,
    }


def _without_skill_reference_blocks(text: str) -> str:
    return re.sub(r"<skill>.*?</skill>", "", text, flags=re.IGNORECASE | re.DOTALL).strip()


def _markdown_title(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        header = re.sub(r"^#{1,6}\s+", "", stripped).strip()
        header = re.sub(r"^[-*]\s+", "", header).strip()
        return _limit_text(header, 90)
    return ""


def _workflow_steps(
    *,
    skill: str,
    prompt: str,
    response: str,
    changed_files: list[str],
    markdown_content: str,
    markdown_path: str,
) -> list[dict[str, Any]]:
    combined = f"{prompt}\n{response}"
    outcome_text = response.strip() or combined
    steps = [
        _step(
            "preflight",
            "Preflight",
            "저장소 상태, 기준 브랜치, review 명령 가능 여부를 확인합니다.",
            _status_by_keywords(outcome_text, ["git status", "preflight", "remote", "branch"], default="unknown"),
            detail=_lines_near_keywords(outcome_text, ["git status", "preflight", "remote", "branch"]),
        ),
        _step(
            "markdown",
            "Markdown 명령 해석",
            "Markdown 파일 또는 현재 요청을 하나의 구현 단위로 읽습니다.",
            "completed",
            detail=markdown_content or markdown_path,
        ),
        _step(
            "branch",
            "작업 브랜치 준비",
            "Markdown 단위별 작업 브랜치를 기준 브랜치에서 준비합니다.",
            _branch_step_status(outcome_text),
            detail=_lines_near_keywords(outcome_text, ["branch", "브랜치", "worktree"]),
        ),
        _step(
            "implementation",
            "구현 작업",
            _implementation_summary(outcome_text, changed_files),
            "completed" if changed_files or _has_any(outcome_text, ["구현", "implemented", "updated", "수정"]) else "unknown",
            detail=_lines_near_keywords(
                outcome_text,
                ["구현", "수정", "추가", "변경", "implemented", "updated", "changed"],
            ),
            files=changed_files[:8],
        ),
        _step(
            "review",
            "리뷰 실행",
            _review_summary(outcome_text),
            _review_status(outcome_text),
            detail=_lines_near_keywords(
                outcome_text,
                [
                    "codex review",
                    "/review",
                    "review:",
                    "리뷰:",
                    "리뷰 결과",
                    "검토 결과",
                    "finding",
                    "actionable",
                    "findings",
                ],
            ),
        ),
        _step(
            "review_fix",
            "리뷰 반영",
            _review_fix_summary(outcome_text),
            _review_fix_status(outcome_text),
            detail=_lines_near_keywords(
                outcome_text,
                ["리뷰 반영", "fixed", "addressed", "수정 완료", "고쳤", "해결", "반영"],
            ),
            files=changed_files[:8],
        ),
        _step(
            "verification",
            "검증",
            _verification_summary(outcome_text),
            _verification_status(outcome_text),
            detail=_lines_near_keywords(
                outcome_text,
                ["pytest", "typecheck", "npm run", "검증", "테스트", "test", "passed"],
            ),
        ),
        _step(
            "commit",
            "커밋",
            "해당 Markdown 단위에 속한 파일만 커밋합니다.",
            _commit_status(outcome_text),
            detail=_lines_near_keywords(outcome_text, ["commit", "committed", "커밋"]),
        ),
    ]

    if skill == "markdown-branch-push":
        steps.extend(
            [
                _step(
                    "push",
                    "브랜치 Push",
                    "파일 브랜치를 origin에 push합니다.",
                    _push_status(outcome_text),
                    detail=_lines_near_keywords(outcome_text, ["pushed", "branch push", "브랜치 push", "브랜치 푸시", "push"]),
                ),
                _step(
                    "merge",
                    "main 병합/Push",
                    "파일 브랜치를 main에 통합하고 main을 push합니다.",
                    _merge_status(outcome_text),
                    detail=_lines_near_keywords(outcome_text, ["merged", "main push", "main-pushed", "main 병합", "merge", "병합"]),
                ),
            ]
        )

    return steps


def _step(
    kind: str,
    label: str,
    summary: str,
    status: str,
    *,
    detail: str = "",
    files: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": kind,
        "kind": kind,
        "label": label,
        "summary": summary,
        "detail": detail,
        "status": status,
        "files": files or [],
    }


def _status_by_keywords(text: str, keywords: list[str], *, default: str = "unknown") -> str:
    return "completed" if _has_any(text, keywords) else default


def _branch_step_status(text: str) -> str:
    if _has_any(text, ["branch", "브랜치", "worktree"]):
        return "completed"
    return "unknown"


def _review_status(text: str) -> str:
    if _has_any(
        text,
        [
            "codex review",
            "/review",
            "finding",
            "findings",
            "actionable",
            "리뷰:",
            "리뷰 결과",
            "리뷰 finding",
            "검토 결과",
            "review:",
        ],
    ):
        return "completed"
    return "pending"


def _review_fix_status(text: str) -> str:
    if _has_any(text, ["리뷰 반영", "review_fix", "fixed", "addressed", "수정 완료", "고쳤", "해결"]):
        return "completed"
    if _review_status(text) == "completed":
        return "skipped"
    return "pending"


def _verification_status(text: str) -> str:
    if _has_any(text, ["pytest", "typecheck", "npm run", "test", "검증", "테스트"]):
        return "completed"
    return "pending"


def _commit_status(text: str) -> str:
    lower = text.lower()
    if _has_any(lower, ["no commit", "not commit", "커밋하지", "커밋 없음"]):
        return "skipped"
    if _has_any(lower, ["commit", "committed", "커밋"]):
        return "completed"
    return "pending"


def _push_status(text: str) -> str:
    lower = text.lower()
    if _has_any(lower, ["no push", "not push", "push하지", "푸시하지", "푸시 없음"]):
        return "skipped"
    if _has_any(lower, ["pushed", "branch push", "브랜치 push", "브랜치 푸시"]):
        return "completed"
    return "pending"


def _merge_status(text: str) -> str:
    lower = text.lower()
    if _has_any(lower, ["no main", "not merge", "merge하지", "병합하지", "main 통합 없음"]):
        return "skipped"
    if _has_any(lower, ["merged", "main push", "main-pushed", "main 병합", "main push"]):
        return "completed"
    return "pending"


def _implementation_summary(text: str, changed_files: list[str]) -> str:
    item = _extract_line(text, ["구현", "수정", "추가", "변경", "implemented", "updated"])
    if item:
        return item
    if changed_files:
        return f"{len(changed_files)}개 파일을 변경했습니다."
    return "구현 작업 내용을 아직 diff에서 찾지 못했습니다."


def _review_summary(text: str) -> str:
    item = _extract_line(
        text,
        [
            "codex review",
            "/review",
            "finding",
            "findings",
            "actionable",
            "리뷰:",
            "리뷰 결과",
            "검토 결과",
            "review:",
        ],
    )
    return item or "리뷰 명령을 실행해 correctness/design finding을 확인합니다."


def _review_fix_summary(text: str) -> str:
    item = _extract_line(text, ["반영", "fixed", "addressed", "수정 완료", "해결"])
    return item or "리뷰 finding이 있으면 수정하고 다시 리뷰합니다."


def _verification_summary(text: str) -> str:
    item = _extract_line(text, ["pytest", "typecheck", "npm run", "검증", "테스트", "test"])
    return item or "리뷰 이후 필요한 좁은 검증을 실행합니다."


def _extract_line(text: str, keywords: list[str]) -> str:
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        normalized = re.sub(r"^[-*]\s+", "", line)
        normalized = re.sub(r"^\d+\.\s+", "", normalized)
        if _has_any(normalized, keywords):
            return _limit_text(normalized, 180)
    return ""


def _lines_near_keywords(text: str, keywords: list[str], *, limit: int = 8) -> str:
    """Return compact outcome lines for a workflow node.

    Skill instructions often contain the same words as a final result. This
    helper is intentionally fed the assistant response first, so the node detail
    describes what actually happened in the captured turn.
    """
    output: list[str] = []
    carry = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            carry = 0
            continue

        normalized = re.sub(r"^[-*]\s+", "", line)
        normalized = re.sub(r"^\d+\.\s+", "", normalized)
        has_keyword = _has_any(normalized, keywords)
        looks_like_followup = bool(re.match(r"^(?:\[?P[0-3]\]?|::code-comment|\-|\*)", line, re.IGNORECASE))
        if has_keyword:
            output.append(_limit_text(normalized, 240))
            carry = 4
        elif carry > 0 and looks_like_followup:
            output.append(_limit_text(normalized, 240))
            carry -= 1

        if len(output) >= limit:
            break

    return "\n".join(_unique(output))


def _changed_files(graph: dict[str, Any]) -> list[str]:
    nodes = graph.get("nodes") if isinstance(graph.get("nodes"), list) else []
    files: list[str] = []
    for node in nodes:
        if (
            isinstance(node, dict)
            and node.get("kind") == "changed"
            and node.get("symbol_kind") == "file"
            and node.get("file")
        ):
            files.append(str(node["file"]))
    return _unique(files)


def _branch_name(text: str) -> str:
    patterns = [
        r"(?:branch|브랜치)\s*[:=]\s*`?(?P<branch>[\w./-]+)`?",
        r"`(?P<branch>codex/[\w./-]+)`",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group("branch").strip("`")
    return ""


def _command_label(skill: str, unit: dict[str, str]) -> str:
    title = unit.get("title") or unit.get("path") or "현재 요청"
    return f"{WORKFLOW_SKILL_LABELS.get(skill, skill)} · {title}"


def _run_status(steps: list[dict[str, Any]]) -> str:
    statuses = {str(step.get("status") or "") for step in steps}
    if "blocked" in statuses:
        return "blocked"
    if "pending" in statuses or "unknown" in statuses:
        return "in_progress"
    return "completed"


def _has_any(text: str, keywords: list[str]) -> bool:
    lower = text.lower()
    return any(keyword.lower() in lower for keyword in keywords)


def _limit_text(value: str, limit: int = MAX_MARKDOWN_CHARS) -> str:
    value = value.strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-")
    return safe[:80] or "request"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output
