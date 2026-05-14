"""Lean git diff collection for codeflow-light.

Supports three change sources:
  - working: uncommitted changes vs HEAD (default)
  - staged:  staged changes vs HEAD
  - range:   <base>..<head> commit range
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

ChangeSource = Literal["working", "staged", "range"]

MAX_PATCH_CHARS = 140_000
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


def _resolve_root(raw: str) -> Path:
    root = Path(raw).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"project_root is not a directory: {raw}")
    try:
        top = _run_git(root, ["rev-parse", "--show-toplevel"], timeout=10).strip()
        return Path(top).resolve()
    except Exception:
        return root


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
            current_hunk.added_lines.append((new_line_no, line[1:]))
            new_line_no += 1
        elif line.startswith("-") and not line.startswith("---"):
            current_hunk.removed_lines.append((old_line_no, line[1:]))
            old_line_no += 1
        elif line.startswith(" "):
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


def collect_diff(
    project_root: str,
    source: ChangeSource = "working",
    base_ref: Optional[str] = None,
    head_ref: Optional[str] = None,
) -> GitDiffResult:
    root = _resolve_root(project_root)
    warnings: list[str] = []

    if source == "range":
        if not base_ref:
            raise ValueError("source=range requires base_ref")
        head = head_ref or "HEAD"
        args = ["diff", "--unified=3", f"{base_ref}..{head}"]
    elif source == "staged":
        args = ["diff", "--cached", "--unified=3"]
    else:
        args = ["diff", "--unified=3", "HEAD"]

    raw_patch = _run_git(root, args, timeout=60)

    if len(raw_patch) > MAX_PATCH_CHARS:
        warnings.append(f"patch truncated at {MAX_PATCH_CHARS} chars")
        raw_patch = raw_patch[:MAX_PATCH_CHARS]

    files = _parse_unified_diff(raw_patch)

    if source == "working":
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
            files.append(
                FileChange(
                    path=path,
                    status="added",
                    language=_guess_language(path),
                )
            )

    return GitDiffResult(
        source=source,
        base_ref=base_ref,
        head_ref=head_ref,
        project_root=str(root),
        files=files,
        raw_patch=raw_patch,
        warnings=warnings,
    )


def read_file_content(project_root: str, path: str, max_chars: int = MAX_FILE_CONTENT_CHARS) -> str:
    root = _resolve_root(project_root)
    file_path = root / path
    if not file_path.exists() or not file_path.is_file():
        return ""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    if len(content) > max_chars:
        return content[:max_chars] + f"\n\n[truncated at {max_chars} chars]"
    return content
