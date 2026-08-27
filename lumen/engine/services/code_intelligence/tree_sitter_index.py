"""Phase C — Tree-sitter based symbol extraction (official tree-sitter + tree-sitter-python)."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

try:
    from tree_sitter import Language, Node, Parser
    import tree_sitter_python as tspython
    TREE_SITTER_AVAILABLE = True
    _PY_LANGUAGE = Language(tspython.language())
    _PARSER = Parser(_PY_LANGUAGE)
except Exception:  # pragma: no cover
    TREE_SITTER_AVAILABLE = False
    Language = Node = Parser = None  # type: ignore
    tspython = None  # type: ignore
    _PY_LANGUAGE = None
    _PARSER = None

_SKIP_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "node_modules",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    "dist",
    "build",
    ".eggs",
}


@dataclass
class Symbol:
    id: str
    kind: str  # module|class|function|method|import
    name: str
    path: str
    start_line: int
    end_line: int
    parent_id: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "parent_id": self.parent_id,
            "extras": dict(self.extras),
        }


def _sid(path: str, kind: str, name: str, line: int) -> str:
    raw = f"{path}:{kind}:{name}:{line}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def _node_text(source: bytes, node: Node) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


def _iter_py_files(root: Path, *, max_files: int = 2000) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.py"):
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        if not p.is_file():
            continue
        out.append(p)
        if len(out) >= max_files:
            break
    return out


def parse_python_source(source: str | bytes, *, path: str = "<memory>") -> list[Symbol]:
    data = source.encode("utf-8") if isinstance(source, str) else source
    tree = _PARSER.parse(data)
    root = tree.root_node
    symbols: list[Symbol] = []
    mod_id = _sid(path, "module", Path(path).stem, 1)
    symbols.append(
        Symbol(
            id=mod_id,
            kind="module",
            name=Path(path).stem,
            path=path,
            start_line=1,
            end_line=max(1, data.count(b"\n") + 1),
        )
    )

    def walk(node: Node, parent_class: str | None = None, parent_id: str | None = None) -> None:
        parent_id = parent_id or mod_id
        t = node.type
        if t == "class_definition":
            name_node = node.child_by_field_name("name")
            name = _node_text(data, name_node) if name_node else "?"
            sid = _sid(path, "class", name, node.start_point[0] + 1)
            symbols.append(
                Symbol(
                    id=sid,
                    kind="class",
                    name=name,
                    path=path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    parent_id=parent_id,
                )
            )
            for ch in node.children:
                walk(ch, parent_class=name, parent_id=sid)
            return
        if t == "function_definition":
            name_node = node.child_by_field_name("name")
            name = _node_text(data, name_node) if name_node else "?"
            kind = "method" if parent_class else "function"
            sid = _sid(path, kind, f"{parent_class+'.' if parent_class else ''}{name}", node.start_point[0] + 1)
            symbols.append(
                Symbol(
                    id=sid,
                    kind=kind,
                    name=f"{parent_class}.{name}" if parent_class else name,
                    path=path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    parent_id=parent_id,
                )
            )
            return
        if t in {"import_statement", "import_from_statement"}:
            text = _node_text(data, node).strip()
            sid = _sid(path, "import", text[:80], node.start_point[0] + 1)
            symbols.append(
                Symbol(
                    id=sid,
                    kind="import",
                    name=text[:120],
                    path=path,
                    start_line=node.start_point[0] + 1,
                    end_line=node.end_point[0] + 1,
                    parent_id=mod_id,
                    extras={"raw": text[:300]},
                )
            )
            return
        for ch in node.children:
            walk(ch, parent_class=parent_class, parent_id=parent_id)

    walk(root)
    return symbols


def index_python_repo(root: str | Path, *, max_files: int = 2000) -> dict[str, Any]:
    root_p = Path(root).resolve()
    all_syms: list[Symbol] = []
    files_indexed = 0
    errors: list[str] = []
    for fp in _iter_py_files(root_p, max_files=max_files):
        rel = fp.relative_to(root_p).as_posix()
        try:
            src = fp.read_bytes()
            if len(src) > 1_500_000:
                errors.append(f"skip_large:{rel}")
                continue
            all_syms.extend(parse_python_source(src, path=rel))
            files_indexed += 1
        except Exception as exc:
            errors.append(f"{rel}:{type(exc).__name__}")
    return {
        "root": str(root_p),
        "files_indexed": files_indexed,
        "symbol_count": len(all_syms),
        "symbols": [s.to_dict() for s in all_syms],
        "errors": errors[:50],
        "engine": "tree-sitter-python",
    }


__all__ = ["Symbol", "parse_python_source", "index_python_repo"]
