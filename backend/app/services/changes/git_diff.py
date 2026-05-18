"""Lean git diff collection for codeflow-light.

Supports three change sources:
  - working: uncommitted changes vs HEAD (default)
  - staged:  staged changes vs HEAD
  - range:   <base>..<head> commit range
  - branch:  current branch/worktree changes vs merge-base with base branch
"""
from __future__ import annotations

import re
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

ChangeSource = Literal["working", "staged", "range", "branch"]

MAX_PATCH_CHARS = 1_000_000
MAX_FILE_CONTENT_CHARS = 40_000


@dataclass
class FileChange:
    path: str
    status: Literal["added", "modified", "deleted", "renamed"]
    old_path: Optional[str] = None
    hunks: list["DiffHunk"] = field(default_factory=list)
    language: str = ""


@dataclass
class DiffHunk:
    old_start: int
    old_lines: int
    new_start: int
    new_lines: int
    added_lines: list[tuple[int, str]] = field(default_factory=list)
    removed_lines: list[tuple[int, str]] = field(default_factory=list)
    lines: list["DiffLine"] = field(default_factory=list)


@dataclass
class DiffLine:
    kind: Literal["context", "added", "removed"]
    old_line: Optional[int]
    new_line: Optional[int]
    text: str


@dataclass
class GitDiffResult:
    source: ChangeSource
    base_ref: Optional[str]
    head_ref: Optional[str]
    project_root: str
    files: list[FileChange]
    raw_patch: str
    warnings: list[str] = field(default_factory=list)


def _run_git(project_root: Path, args: list[str], timeout: int = 30) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(project_root),
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "git command failed").strip())
    return proc.stdout or ""


def _try_git(project_root: Path, args: list[str], timeout: int = 30) -> str:
    try:
        return _run_git(project_root, args, timeout=timeout).strip()
    except Exception:
        return ""


def _resolve_root(raw: str) -> Path:
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project_root is not a directory: {raw}")
    try:
        top = _run_git(root, ["rev-parse", "--show-toplevel"], timeout=10).strip()
        return Path(top).resolve()
    except Exception:
        return root


def resolve_project_root(raw: str) -> str:
    """Resolve a path to the git top level when it belongs to a repository."""
    return str(_resolve_root(raw))


_HUNK_HEADER = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
_DIFF_HEADER = re.compile(r"^diff --git a/(.+?) b/(.+?)$")


def _parse_unified_diff(patch: str) -> list[FileChange]:
    files: list[FileChange] = []
    current: Optional[FileChange] = None
    current_hunk: Optional[DiffHunk] = None
    new_line_no = 0
    old_line_no = 0

    for line in patch.splitlines():
        diff_match = _DIFF_HEADER.match(line)
        if diff_match:
            if current:
                if current_hunk:
                    current.hunks.append(current_hunk)
                files.append(current)
            old_path, new_path = diff_match.group(1), diff_match.group(2)
            current = FileChange(
                path=new_path,
                status="modified",
                old_path=old_path if old_path != new_path else None,
                language=_guess_language(new_path),
            )
            current_hunk = None
            continue

        if current is None:
            continue

        if line.startswith("new file mode"):
            current.status = "added"
        elif line.startswith("deleted file mode"):
            current.status = "deleted"
        elif line.startswith("rename from") or line.startswith("rename to"):
            current.status = "renamed"

        hunk_match = _HUNK_HEADER.match(line)
        if hunk_match:
            if current_hunk:
                current.hunks.append(current_hunk)
            old_start = int(hunk_match.group(1))
            old_lines = int(hunk_match.group(2) or "1")
            new_start = int(hunk_match.group(3))
            new_lines = int(hunk_match.group(4) or "1")
            current_hunk = DiffHunk(
                old_start=old_start,
                old_lines=old_lines,
                new_start=new_start,
                new_lines=new_lines,
            )
            old_line_no = old_start
            new_line_no = new_start
            continue

        if current_hunk is None:
            continue

        if line.startswith("+") and not line.startswith("+++"):
            current_hunk.lines.append(
                DiffLine(kind="added", old_line=None, new_line=new_line_no, text=line[1:])
            )
            current_hunk.added_lines.append((new_line_no, line[1:]))
            new_line_no += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_hunk.lines.append(
                DiffLine(kind="removed", old_line=old_line_no, new_line=None, text=line[1:])
            )
            current_hunk.removed_lines.append((old_line_no, line[1:]))
            old_line_no += 1
        elif line.startswith(" "):
            current_hunk.lines.append(
                DiffLine(
                    kind="context",
                    old_line=old_line_no,
                    new_line=new_line_no,
                    text=line[1:],
                )
            )
            new_line_no += 1
            old_line_no += 1

    if current:
        if current_hunk:
            current.hunks.append(current_hunk)
        files.append(current)
    return files


_LANG_BY_EXT: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rs": "rust",
    ".rb": "ruby",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".kt": "kotlin",
    ".swift": "swift",
    ".php": "php",
    ".sql": "sql",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}


def _guess_language(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return _LANG_BY_EXT.get(suffix, "")


def _resolve_branch_base(root: Path, requested_base: Optional[str]) -> str:
    if requested_base:
        return requested_base

    candidates: list[str] = []
    origin_head = _try_git(root, ["symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"], timeout=10)
    if origin_head:
        candidates.append(origin_head)

    candidates.extend(["origin/main", "origin/master", "main", "master"])
    upstream = _try_git(root, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"], timeout=10)
    if upstream:
        candidates.append(upstream)

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if _try_git(root, ["rev-parse", "--verify", candidate], timeout=10):
            return candidate
    return "HEAD"


def _resolve_merge_base(root: Path, base_ref: str, head_ref: str) -> str:
    merge_base = _try_git(root, ["merge-base", base_ref, head_ref], timeout=15)
    return merge_base or base_ref


def collect_diff(
    project_root: str,
    source: ChangeSource = "working",
    base_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
) -> GitDiffResult:
    root = _resolve_root(project_root)
    warnings: list[str] = []
    include_worktree_files = source == "working"

    if source == "range":
        if not base_ref:
            raise ValueError("source=range requires base_ref")
        head = head_ref or "HEAD"
        args = ["diff", "--unified=3", f"{base_ref}..{head}"]
    elif source == "branch":
        explicit_head = bool(head_ref and head_ref != "HEAD")
        head = head_ref or "HEAD"
        base = _resolve_branch_base(root, base_ref)
        merge_base = _resolve_merge_base(root, base, head)
        base_ref = base
        head_ref = head
        if explicit_head:
            args = ["diff", "--unified=3", f"{merge_base}..{head}"]
        else:
            include_worktree_files = True
            args = ["diff", "--unified=3", merge_base]
    elif source == "staged":
        args = ["diff", "--cached", "--unified=3"]
    else:
        args = ["diff", "--unified=3", "HEAD"]

    raw_patch = _run_git(root, args, timeout=60)

    if len(raw_patch) > MAX_PATCH_CHARS:
        warnings.append(f"patch truncated at {MAX_PATCH_CHARS} chars")
        raw_patch = raw_patch[:MAX_PATCH_CHARS]

    files = _parse_unified_diff(raw_patch)

    if include_worktree_files:
        try:
            untracked = _run_git(
                root, ["ls-files", "--others", "--exclude-standard"], timeout=15
            ).splitlines()
        except Exception:
            untracked = []
        existing_paths = {f.path for f in files}
        for path in untracked:
            path = path.strip()
            if not path or path in existing_paths:
                continue
            file_change, warning = _untracked_file_change(root, path)
            files.append(file_change)
            if warning:
                warnings.append(warning)

    return GitDiffResult(
        source=source,
        base_ref=base_ref,
        head_ref=head_ref,
        project_root=str(root),
        files=files,
        raw_patch=raw_patch,
        warnings=warnings,
    )


def _untracked_file_change(root: Path, path: str) -> tuple[FileChange, str]:
    file_change = FileChange(
        path=path,
        status="added",
        language=_guess_language(path),
    )
    file_path = root / path
    try:
        file_stat = file_path.lstat()
    except OSError:
        return file_change, f"could not stat untracked file: {path}"

    if file_path.is_symlink():
        display = "symlink target omitted"
        file_change.hunks.append(
            DiffHunk(
                old_start=0,
                old_lines=0,
                new_start=1,
                new_lines=1,
                added_lines=[(1, display)],
                lines=[
                    DiffLine(kind="added", old_line=None, new_line=1, text=display),
                ],
            )
        )
        return file_change, f"untracked symlink skipped without reading target: {path}"

    if not stat.S_ISREG(file_stat.st_mode):
        return file_change, ""

    warning = ""
    read_limit = MAX_FILE_CONTENT_CHARS + 1
    try:
        with file_path.open(encoding="utf-8", errors="replace") as handle:
            content = handle.read(read_limit)
    except Exception:
        return file_change, f"could not read untracked file: {path}"

    if file_stat.st_size > MAX_FILE_CONTENT_CHARS or len(content) > MAX_FILE_CONTENT_CHARS:
        warning = f"untracked file {path} truncated at {MAX_FILE_CONTENT_CHARS} chars"
        content = content[:MAX_FILE_CONTENT_CHARS]

    lines = content.splitlines()
    if lines:
        added_lines = [(index + 1, line) for index, line in enumerate(lines)]
        file_change.hunks.append(
            DiffHunk(
                old_start=0,
                old_lines=0,
                new_start=1,
                new_lines=len(lines),
                added_lines=added_lines,
                lines=[
                    DiffLine(kind="added", old_line=None, new_line=line_no, text=line)
                    for line_no, line in added_lines
                ],
            )
        )
    return file_change, warning


def read_file_content(project_root: str, path: str, max_chars: int = MAX_FILE_CONTENT_CHARS) -> str:
    root = _resolve_root(project_root)
    relative_path = Path(path)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        return ""
    file_path = root / path
    try:
        file_stat = file_path.lstat()
    except OSError:
        return ""
    if file_path.is_symlink() or not stat.S_ISREG(file_stat.st_mode):
        return ""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(content) > max_chars:
        return content[:max_chars] + f"\n\n[truncated at {max_chars} chars]"
    return content
