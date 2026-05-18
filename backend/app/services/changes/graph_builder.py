"""Build the change graph from a parsed git diff.

The graph has three node kinds:
  - changed:  a function/class/file the LLM modified or added
  - affected: a symbol that references a changed symbol (callers)
  - context:  a symbol referenced *by* a changed symbol (callees) when useful

Edges are:
  - modifies:      the change touches this symbol
  - calls:         changed symbol calls another symbol
  - imports:       one file imports another file in the project
  - referenced_by: affected symbol references the changed symbol
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

from .git_diff import FileChange, GitDiffResult, read_file_content
from .symbol_extractor import SymbolSpan, extract_symbols, find_enclosing_symbol


NodeKind = Literal["changed", "affected", "context", "file"]
ChangeStatus = Literal["added", "modified", "deleted", "renamed", "unchanged"]
EdgeKind = Literal[
    "modifies",
    "calls",
    "imports",
    "referenced_by",
    "contains",
    "renamed_from",
]


@dataclass
class ChangeNode:
    id: str
    kind: NodeKind
    label: str
    file: str
    language: str = ""
    symbol_kind: str = ""  # function | method | class | module | file
    status: ChangeStatus = "unchanged"
    start_line: Optional[int] = None
    end_line: Optional[int] = None
    summary: str = ""
    body: str = ""
    snippet: str = ""
    added_lines: int = 0
    removed_lines: int = 0


@dataclass
class ChangeEdge:
    id: str
    source: str
    target: str
    kind: EdgeKind
    label: str = ""
    summary: str = ""
    body: str = ""


@dataclass
class ChangeGraph:
    project_root: str
    source: str
    base_ref: Optional[str]
    head_ref: Optional[str]
    nodes: list[ChangeNode] = field(default_factory=list)
    edges: list[ChangeEdge] = field(default_factory=list)
    narrative: str = ""
    warnings: list[str] = field(default_factory=list)


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_JS_IMPORT_RE = re.compile(
    r"(?m)^\s*import\s+(?:type\s+)?(?:(?P<clause>[^;]*?)\s+from\s+)?"
    r"['\"](?P<module>[^'\"]+)['\"]\s*;?"
)
_JS_EXPORT_FROM_RE = re.compile(
    r"(?m)^\s*export\s+(?:type\s+)?(?P<clause>\*|\{[^;]*?\})\s+from\s+"
    r"['\"](?P<module>[^'\"]+)['\"]\s*;?"
)
_JS_REQUIRE_RE = re.compile(r"\brequire\(\s*['\"](?P<module>[^'\"]+)['\"]\s*\)")
_JS_DYNAMIC_IMPORT_RE = re.compile(r"\bimport\(\s*['\"](?P<module>[^'\"]+)['\"]\s*\)")
_JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".svelte", ".json", ".css")
_PY_EXTENSIONS = (".py",)
MAX_FILE_SNIPPET_CHARS = 24_000


@dataclass(frozen=True)
class _ImportReference:
    module: str
    names: tuple[str, ...] = ()
    level: int = 0
    is_from: bool = False
    line: int = 0
    syntax: str = ""


def _symbol_node_id(file: str, symbol: str) -> str:
    safe_file = file.replace("/", "__").replace(".", "_")
    return f"sym::{safe_file}::{symbol}"


def _file_node_id(file: str) -> str:
    safe_file = file.replace("/", "__").replace(".", "_")
    return f"file::{safe_file}"


def _snippet_for_hunk(file_change: FileChange) -> str:
    lines: list[str] = []
    for hunk in file_change.hunks:
        lines.append(f"@@ -{hunk.old_start},{hunk.old_lines} +{hunk.new_start},{hunk.new_lines} @@")
        if hunk.lines:
            for line in hunk.lines:
                if line.kind == "added":
                    lines.append(f"+ {line.text}")
                elif line.kind == "removed":
                    lines.append(f"- {line.text}")
                else:
                    lines.append(f"  {line.text}")
        else:
            for _ln, text in hunk.removed_lines:
                lines.append(f"- {text}")
            for _ln, text in hunk.added_lines:
                lines.append(f"+ {text}")
        lines.append("")
    return "\n".join(lines).strip()


def _snippet_for_symbol(file_change: FileChange, span: SymbolSpan) -> str:
    keep: list[str] = []
    for hunk in file_change.hunks:
        for ln, text in hunk.added_lines:
            if span.start_line <= ln <= span.end_line:
                keep.append(f"+ {text}")
        for ln, text in hunk.removed_lines:
            if span.start_line <= ln <= span.end_line:
                keep.append(f"- {text}")
    return "\n".join(keep[:80]).strip()


def build_graph(diff: GitDiffResult) -> ChangeGraph:
    graph = ChangeGraph(
        project_root=diff.project_root,
        source=diff.source,
        base_ref=diff.base_ref,
        head_ref=diff.head_ref,
        warnings=list(diff.warnings),
    )

    changed_symbols_by_file: dict[str, list[tuple[SymbolSpan, ChangeNode]]] = {}

    for file_change in diff.files:
        added = sum(len(h.added_lines) for h in file_change.hunks)
        removed = sum(len(h.removed_lines) for h in file_change.hunks)

        file_node_id = _file_node_id(file_change.path)
        file_node = ChangeNode(
            id=file_node_id,
            kind="changed",
            label=Path(file_change.path).name,
            file=file_change.path,
            language=file_change.language,
            symbol_kind="file",
            status=file_change.status,
            snippet=_snippet_for_hunk(file_change)[:MAX_FILE_SNIPPET_CHARS],
            added_lines=added,
            removed_lines=removed,
        )

        if file_change.status == "deleted":
            graph.nodes.append(file_node)
            continue

        content = read_file_content(diff.project_root, file_change.path)
        spans = extract_symbols(content, file_change.language) if content else []

        touched_spans: dict[str, tuple[SymbolSpan, set[int]]] = {}
        for hunk in file_change.hunks:
            for ln, _ in hunk.added_lines:
                span = find_enclosing_symbol(spans, ln)
                if span:
                    entry = touched_spans.setdefault(span.name, (span, set()))
                    entry[1].add(ln)

        if not touched_spans:
            graph.nodes.append(file_node)
            if file_change.old_path and file_change.status == "renamed":
                old_id = _file_node_id(file_change.old_path)
                graph.edges.append(
                    ChangeEdge(
                        id=f"edge::rename::{file_change.path}",
                        source=old_id,
                        target=file_node_id,
                        kind="renamed_from",
                        label="renamed",
                        summary=f"{file_change.old_path} → {file_change.path}",
                    )
                )
            continue

        graph.nodes.append(file_node)
        symbol_nodes: list[tuple[SymbolSpan, ChangeNode]] = []
        for name, (span, lines_touched) in touched_spans.items():
            node_id = _symbol_node_id(file_change.path, name)
            symbol_status: ChangeStatus = "added" if file_change.status == "added" else "modified"
            symbol_node = ChangeNode(
                id=node_id,
                kind="changed",
                label=f"{span.name}",
                file=file_change.path,
                language=file_change.language,
                symbol_kind=span.kind,
                status=symbol_status,
                start_line=span.start_line,
                end_line=span.end_line,
                snippet=_snippet_for_symbol(file_change, span)[:4000],
                added_lines=len(lines_touched),
            )
            graph.nodes.append(symbol_node)
            symbol_nodes.append((span, symbol_node))

            graph.edges.append(
                ChangeEdge(
                    id=f"edge::contains::{node_id}",
                    source=file_node_id,
                    target=node_id,
                    kind="contains",
                    label="contains",
                    summary=f"{file_change.path} contains {span.name}",
                )
            )

        changed_symbols_by_file[file_change.path] = symbol_nodes

    _add_call_edges(graph, diff, changed_symbols_by_file)
    _add_affected_nodes(graph, diff, changed_symbols_by_file)
    _add_import_edges(graph, diff)

    return graph


def _add_call_edges(
    graph: ChangeGraph,
    diff: GitDiffResult,
    changed_symbols_by_file: dict[str, list[tuple[SymbolSpan, ChangeNode]]],
) -> None:
    """For each changed symbol, look at the *added* lines and detect identifiers
    that match other changed symbols. Each match becomes a `calls` edge."""

    all_changed_names: dict[str, list[ChangeNode]] = {}
    for nodes in changed_symbols_by_file.values():
        for _, node in nodes:
            all_changed_names.setdefault(node.label, []).append(node)

    if not all_changed_names:
        return

    for file_change in diff.files:
        symbols = changed_symbols_by_file.get(file_change.path, [])
        if not symbols:
            continue
        for span, node in symbols:
            call_targets: set[str] = set()
            for hunk in file_change.hunks:
                for ln, text in hunk.added_lines:
                    if not (span.start_line <= ln <= span.end_line):
                        continue
                    for token in _IDENT.findall(text):
                        if token == node.label:
                            continue
                        if token in all_changed_names:
                            call_targets.add(token)
            for target_name in call_targets:
                for target_node in all_changed_names[target_name]:
                    if target_node.id == node.id:
                        continue
                    graph.edges.append(
                        ChangeEdge(
                            id=f"edge::calls::{node.id}->{target_node.id}",
                            source=node.id,
                            target=target_node.id,
                            kind="calls",
                            label="calls",
                            summary=f"{node.label} references {target_node.label}",
                        )
                    )


def _add_affected_nodes(
    graph: ChangeGraph,
    diff: GitDiffResult,
    changed_symbols_by_file: dict[str, list[tuple[SymbolSpan, ChangeNode]]],
    max_per_symbol: int = 5,
) -> None:
    """For each changed symbol, grep the repo for references and create
    `affected` nodes for the top files that reference it."""
    if not changed_symbols_by_file:
        return

    project_root = Path(diff.project_root)
    seen_ids: set[str] = {node.id for node in graph.nodes}

    for nodes in changed_symbols_by_file.values():
        for span, node in nodes:
            if node.symbol_kind == "file":
                continue
            references = _grep_references(project_root, node.label, exclude=node.file)
            for ref_file in references[:max_per_symbol]:
                affected_id = _file_node_id(ref_file)
                if affected_id in seen_ids:
                    if not any(
                        edge.source == affected_id and edge.target == node.id
                        for edge in graph.edges
                    ):
                        graph.edges.append(
                            ChangeEdge(
                                id=f"edge::refby::{affected_id}->{node.id}",
                                source=affected_id,
                                target=node.id,
                                kind="referenced_by",
                                label="uses",
                                summary=f"{ref_file} uses {node.label}",
                            )
                        )
                    continue
                graph.nodes.append(
                    ChangeNode(
                        id=affected_id,
                        kind="affected",
                        label=Path(ref_file).name,
                        file=ref_file,
                        language="",
                        symbol_kind="file",
                        status="unchanged",
                        summary=f"references {node.label}",
                    )
                )
                seen_ids.add(affected_id)
                graph.edges.append(
                    ChangeEdge(
                        id=f"edge::refby::{affected_id}->{node.id}",
                        source=affected_id,
                        target=node.id,
                        kind="referenced_by",
                        label="uses",
                        summary=f"{ref_file} uses {node.label}",
                    )
                )


def _add_import_edges(graph: ChangeGraph, diff: GitDiffResult, max_edges: int = 120) -> None:
    """Add file-level import edges for project-local imports.

    Codeflow Light intentionally avoids a full language server. This resolver
    handles the import forms most common in the projects Codex/Claude edit:
    Python imports, TS/JS/React relative imports, and a few frontend aliases
    (`@/`, `~/`, `$lib/`).
    """
    project_root = Path(diff.project_root)
    nodes_by_file = {
        node.file: node for node in graph.nodes if node.symbol_kind == "file" and node.file
    }
    seen_node_ids: set[str] = {node.id for node in graph.nodes}
    seen_edge_ids: set[str] = {edge.id for edge in graph.edges}
    edges_added = 0

    source_nodes = [
        node
        for node in graph.nodes
        if node.symbol_kind == "file" and node.status != "deleted" and node.file
    ]
    changed_files = {
        node.file
        for node in graph.nodes
        if node.symbol_kind == "file" and node.kind == "changed" and node.file
    }
    if not changed_files:
        return

    source_files_seen = {node.file for node in source_nodes}

    for source_node in source_nodes:
        if edges_added >= max_edges:
            graph.warnings.append(f"import edges truncated at {max_edges}")
            return

        for ref, target_file in _resolved_file_imports(project_root, diff, source_node.file, source_node.language):
            if edges_added >= max_edges:
                graph.warnings.append(f"import edges truncated at {max_edges}")
                return

            target_node = nodes_by_file.get(target_file)
            if not target_node:
                target_node = ChangeNode(
                    id=_file_node_id(target_file),
                    kind="context",
                    label=Path(target_file).name,
                    file=target_file,
                    language=_language_for_path(target_file),
                    symbol_kind="file",
                    status="unchanged",
                    summary=f"{source_node.file}에서 import됨",
                )
                if target_node.id not in seen_node_ids:
                    graph.nodes.append(target_node)
                    seen_node_ids.add(target_node.id)
                nodes_by_file[target_file] = target_node

            edge_id = (
                f"edge::imports::{source_node.id}->{target_node.id}::"
                f"{_safe_edge_part(ref.module)}"
            )
            if edge_id in seen_edge_ids:
                continue

            imported_items = ", ".join(ref.names) if ref.names else ref.module
            edge_body = [
                f"- **관계**: import",
                f"- **출발 파일**: `{source_node.file}`",
                f"- **가져오는 파일**: `{target_file}`",
                f"- **가져오는 기능**: `{imported_items}`",
            ]
            if ref.line:
                edge_body.append(f"- **import 위치**: {ref.line} 행")
            if ref.syntax:
                edge_body.append(f"- **import 문**: `{ref.syntax}`")

            graph.edges.append(
                ChangeEdge(
                    id=edge_id,
                    source=source_node.id,
                    target=target_node.id,
                    kind="imports",
                    label="imports",
                    summary=f"`{source_node.file}` 가 `{target_file}` 를 import합니다.",
                    body="\n".join(edge_body),
                )
            )
            seen_edge_ids.add(edge_id)
            edges_added += 1

    for importer_file in _repo_code_files(project_root):
        if edges_added >= max_edges:
            graph.warnings.append(f"import edges truncated at {max_edges}")
            return
        if importer_file in source_files_seen:
            continue

        importer_language = _language_for_path(importer_file)
        for ref, target_file in _resolved_file_imports(project_root, diff, importer_file, importer_language):
            if target_file not in changed_files or target_file == importer_file:
                continue

            importer_node = nodes_by_file.get(importer_file)
            if not importer_node:
                importer_node = ChangeNode(
                    id=_file_node_id(importer_file),
                    kind="affected",
                    label=Path(importer_file).name,
                    file=importer_file,
                    language=importer_language,
                    symbol_kind="file",
                    status="unchanged",
                    summary=f"{target_file}를 import해서 사용함",
                )
                if importer_node.id not in seen_node_ids:
                    graph.nodes.append(importer_node)
                    seen_node_ids.add(importer_node.id)
                nodes_by_file[importer_file] = importer_node

            target_node = nodes_by_file.get(target_file)
            if not target_node:
                continue

            edge_id = (
                f"edge::imports::{importer_node.id}->{target_node.id}::"
                f"{_safe_edge_part(ref.module)}"
            )
            if edge_id in seen_edge_ids:
                continue

            imported_items = ", ".join(ref.names) if ref.names else ref.module
            graph.edges.append(
                ChangeEdge(
                    id=edge_id,
                    source=importer_node.id,
                    target=target_node.id,
                    kind="imports",
                    label="imports",
                    summary=f"`{importer_file}` 가 변경 파일 `{target_file}` 를 import해서 사용합니다.",
                    body="\n".join(
                        [
                            "- **관계**: import 사용처",
                            f"- **사용하는 파일**: `{importer_file}`",
                            f"- **변경 파일**: `{target_file}`",
                            f"- **가져오는 기능**: `{imported_items}`",
                            f"- **import 위치**: {ref.line} 행" if ref.line else "",
                            f"- **import 문**: `{ref.syntax}`" if ref.syntax else "",
                        ]
                    ).strip(),
                )
            )
            seen_edge_ids.add(edge_id)
            edges_added += 1


def _resolved_file_imports(
    project_root: Path,
    diff: GitDiffResult,
    source_file: str,
    language: str,
) -> list[tuple[_ImportReference, str]]:
    content = read_file_content(diff.project_root, source_file)
    if not content:
        return []

    resolved: list[tuple[_ImportReference, str]] = []
    for ref in _extract_imports(content, source_file, language):
        target_file = _resolve_import_reference(project_root, source_file, ref)
        if target_file and target_file != source_file:
            resolved.append((ref, target_file))
    return resolved


def _extract_imports(content: str, file_path: str, language: str) -> list[_ImportReference]:
    suffix = Path(file_path).suffix.lower()
    if language == "python" or suffix == ".py":
        return _extract_python_imports(content)
    if suffix in _JS_EXTENSIONS or language in {"javascript", "typescript"}:
        return _extract_js_imports(content)
    return []


def _extract_python_imports(content: str) -> list[_ImportReference]:
    try:
        import ast

        tree = ast.parse(content)
    except Exception:
        return []

    refs: list[_ImportReference] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                refs.append(
                    _ImportReference(
                        module=alias.name,
                        names=(alias.asname or alias.name,),
                        line=getattr(node, "lineno", 0),
                        syntax=f"import {alias.name}",
                    )
                )
        elif isinstance(node, ast.ImportFrom):
            names = tuple(alias.name for alias in node.names if alias.name)
            module = node.module or ""
            dots = "." * int(getattr(node, "level", 0) or 0)
            imported = ", ".join(names) if names else "*"
            refs.append(
                _ImportReference(
                    module=module,
                    names=names,
                    level=int(getattr(node, "level", 0) or 0),
                    is_from=True,
                    line=getattr(node, "lineno", 0),
                    syntax=f"from {dots}{module} import {imported}",
                )
            )
    return refs


def _extract_js_imports(content: str) -> list[_ImportReference]:
    refs: list[_ImportReference] = []
    for regex in (_JS_IMPORT_RE, _JS_EXPORT_FROM_RE):
        for match in regex.finditer(content):
            module = match.group("module")
            clause = (match.groupdict().get("clause") or "").strip()
            refs.append(
                _ImportReference(
                    module=module,
                    names=tuple(_extract_js_import_names(clause)),
                    line=content.count("\n", 0, match.start()) + 1,
                    syntax=match.group(0).strip().replace("\n", " "),
                )
            )
    for regex in (_JS_REQUIRE_RE, _JS_DYNAMIC_IMPORT_RE):
        for match in regex.finditer(content):
            module = match.group("module")
            refs.append(
                _ImportReference(
                    module=module,
                    line=content.count("\n", 0, match.start()) + 1,
                    syntax=match.group(0).strip(),
                )
            )
    return refs


def _extract_js_import_names(clause: str) -> list[str]:
    if not clause:
        return []
    names: list[str] = []
    cleaned = clause.replace("type ", "")
    cleaned = cleaned.replace("{", "").replace("}", "").replace("* as", "")
    for part in cleaned.split(","):
        name = part.strip()
        if not name:
            continue
        if " as " in name:
            name = name.split(" as ", 1)[0].strip()
        if name:
            names.append(name)
    return names[:12]


def _resolve_import_reference(
    project_root: Path,
    source_file: str,
    ref: _ImportReference,
) -> Optional[str]:
    if Path(source_file).suffix.lower() == ".py":
        return _resolve_python_reference(project_root, source_file, ref)
    return _resolve_js_reference(project_root, source_file, ref)


def _resolve_js_reference(project_root: Path, source_file: str, ref: _ImportReference) -> Optional[str]:
    module = ref.module
    source_parent = (project_root / source_file).parent
    candidates: list[Path] = []

    if module.startswith("."):
        candidates.append((source_parent / module).resolve())
    elif module.startswith("@/"):
        candidates.extend((root / module[2:]).resolve() for root in _js_alias_roots(project_root, source_file))
    elif module.startswith("~/"):
        candidates.extend((root / module[2:]).resolve() for root in _js_alias_roots(project_root, source_file))
    elif module.startswith("$lib/"):
        candidates.extend(
            (root / "lib" / module[len("$lib/") :]).resolve()
            for root in _js_alias_roots(project_root, source_file)
        )
    elif "/" in module:
        candidates.append((project_root / module).resolve())
        candidates.append((project_root / "src" / module).resolve())

    for candidate in candidates:
        resolved = _resolve_existing_path(project_root, candidate, _JS_EXTENSIONS)
        if resolved:
            return resolved
    return None


def _js_alias_roots(project_root: Path, source_file: str) -> list[Path]:
    roots: list[Path] = []
    source_parts = Path(source_file).parts
    if "src" in source_parts:
        src_index = source_parts.index("src")
        roots.append(project_root.joinpath(*source_parts[: src_index + 1]))
    roots.append(project_root / "src")
    roots.append(project_root / "frontend" / "src")
    return _unique_paths(roots)


def _unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(resolved)
    return unique


def _resolve_python_reference(
    project_root: Path,
    source_file: str,
    ref: _ImportReference,
) -> Optional[str]:
    modules: list[str] = []
    base_module = _resolve_python_module_name(source_file, ref.module, ref.level)

    if ref.is_from:
        for name in ref.names:
            if name == "*":
                continue
            modules.append(f"{base_module}.{name}" if base_module else name)
        if base_module:
            modules.append(base_module)
    elif ref.module:
        modules.append(ref.module)

    seen: set[str] = set()
    for module in modules:
        module = module.strip(".")
        if not module or module in seen:
            continue
        seen.add(module)
        module_path = module.replace(".", "/")
        for root in _python_import_roots(project_root, source_file, module):
            candidate = (root / module_path).resolve()
            resolved = _resolve_existing_path(project_root, candidate, _PY_EXTENSIONS)
            if resolved:
                return resolved
    return None


def _python_import_roots(project_root: Path, source_file: str, module: str) -> list[Path]:
    roots: list[Path] = [project_root]
    first_module = module.split(".", 1)[0] if module else ""
    source_parts = Path(source_file).parts

    if source_parts:
        top_level = project_root / source_parts[0]
        if first_module and (top_level / first_module).exists():
            roots.append(top_level)

    for common in ("backend", "src"):
        root = project_root / common
        if first_module and (root / first_module).exists():
            roots.append(root)

    seen: set[Path] = set()
    unique_roots: list[Path] = []
    for root in roots:
        resolved = root.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_roots.append(resolved)
    return unique_roots


def _resolve_python_module_name(source_file: str, module: str, level: int) -> str:
    if level <= 0:
        return module or ""

    source_path = Path(source_file)
    package_parts = list(source_path.parent.parts)
    if source_path.name == "__init__.py":
        package_parts = list(source_path.parent.parts)
    ascend = max(level - 1, 0)
    if ascend:
        package_parts = package_parts[:-ascend] if ascend < len(package_parts) else []
    if module:
        package_parts.extend(part for part in module.split(".") if part)
    return ".".join(package_parts)


def _resolve_existing_path(project_root: Path, candidate: Path, extensions: tuple[str, ...]) -> Optional[str]:
    paths: list[Path] = []
    if candidate.suffix:
        paths.append(candidate)
    else:
        paths.extend(Path(str(candidate) + ext) for ext in extensions)
        paths.append(candidate)

    if candidate.is_dir() or not candidate.suffix:
        for ext in extensions:
            paths.append(candidate / f"index{ext}")
        if ".py" in extensions:
            paths.append(candidate / "__init__.py")

    for path in paths:
        try:
            resolved = path.resolve()
            resolved.relative_to(project_root.resolve())
        except Exception:
            continue
        if resolved.is_file():
            return resolved.relative_to(project_root.resolve()).as_posix()
    return None


def _safe_edge_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value or "module")[:80]


def _language_for_path(path: str) -> str:
    suffix = Path(path).suffix.lower()
    return {
        ".py": "python",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".js": "javascript",
        ".jsx": "javascript",
        ".mjs": "javascript",
        ".cjs": "javascript",
        ".svelte": "svelte",
        ".json": "json",
        ".css": "css",
    }.get(suffix, "")


def _repo_code_files(project_root: Path, limit: int = 2000) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "ls-files"],
            cwd=str(project_root),
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode != 0:
        return []
    allowed = set(_JS_EXTENSIONS + _PY_EXTENSIONS)
    files = [
        line.strip()
        for line in (proc.stdout or "").splitlines()
        if line.strip() and Path(line.strip()).suffix.lower() in allowed
    ]
    return files[:limit]


def _grep_references(project_root: Path, symbol: str, exclude: str, limit: int = 20) -> list[str]:
    if not symbol or len(symbol) < 3:
        return []
    pattern = r"\b" + re.escape(symbol) + r"\b"
    try:
        proc = subprocess.run(
            ["git", "grep", "-l", "-E", pattern],
            cwd=str(project_root),
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return []
    if proc.returncode not in (0, 1):
        return []
    paths = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
    return [p for p in paths if p != exclude][:limit]
