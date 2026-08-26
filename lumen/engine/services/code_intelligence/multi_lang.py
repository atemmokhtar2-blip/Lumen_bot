"""Multi-language Tree-sitter indexing — Python + JavaScript (world-class foundation).

Scope: bots (Telegram/Discord/WhatsApp), web apps, scripts — not Telegram-only.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from tree_sitter import Language, Parser

import tree_sitter_python as tspython

try:
    import tree_sitter_javascript as tsjavascript
    _JS_LANG = Language(tsjavascript.language())
except Exception:  # pragma: no cover
    _JS_LANG = None

def _opt_lang(mod_name: str):
    try:
        mod = __import__(mod_name, fromlist=["language"])
        return Language(mod.language())
    except Exception:
        return None

_TS_LANG = _opt_lang("tree_sitter_typescript")
_GO_LANG = _opt_lang("tree_sitter_go")
_JAVA_LANG = _opt_lang("tree_sitter_java")
_RUST_LANG = _opt_lang("tree_sitter_rust")
_C_LANG = _opt_lang("tree_sitter_c")
_CPP_LANG = _opt_lang("tree_sitter_cpp")

_PY_LANG = Language(tspython.language())

_SKIP = {
    ".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build",
    ".next", ".lumen_code_index", ".tox", ".mypy_cache",
}

_LANG_BY_EXT: dict[str, tuple[str, Language | None]] = {
    ".py": ("python", _PY_LANG),
    ".js": ("javascript", _JS_LANG),
    ".jsx": ("javascript", _JS_LANG),
    ".mjs": ("javascript", _JS_LANG),
    ".cjs": ("javascript", _JS_LANG),
    ".ts": ("typescript", _TS_LANG),
    ".tsx": ("typescript", _TS_LANG),
    ".go": ("go", _GO_LANG),
    ".java": ("java", _JAVA_LANG),
    ".rs": ("rust", _RUST_LANG),
    ".c": ("c", _C_LANG),
    ".h": ("c", _C_LANG),
    ".cpp": ("cpp", _CPP_LANG),
    ".cc": ("cpp", _CPP_LANG),
    ".hpp": ("cpp", _CPP_LANG),
}


def _sid(path: str, kind: str, name: str, line: int) -> str:
    return hashlib.sha1(f"{path}:{kind}:{name}:{line}".encode()).hexdigest()[:16]


def _extract_python(path: str, data: bytes) -> list[dict[str, Any]]:
    from .tree_sitter_index import parse_python_source
    return [s.to_dict() for s in parse_python_source(data, path=path)]


def _walk_js_names(source: bytes, path: str) -> list[dict[str, Any]]:
    if _JS_LANG is None:
        return []
    parser = Parser(_JS_LANG)
    tree = parser.parse(source)
    root = tree.root_node
    out: list[dict[str, Any]] = []
    mod_id = _sid(path, "module", Path(path).stem, 1)
    out.append(
        {
            "id": mod_id,
            "kind": "module",
            "name": Path(path).stem,
            "path": path,
            "start_line": 1,
            "end_line": source.count(b"\n") + 1,
            "parent_id": None,
            "extras": {"lang": "javascript"},
        }
    )

    def text(n) -> str:
        return source[n.start_byte : n.end_byte].decode("utf-8", errors="replace")

    def walk(node, parent_id: str = mod_id) -> None:
        t = node.type
        if t in {"function_declaration", "method_definition", "class_declaration"}:
            name_node = node.child_by_field_name("name")
            name = text(name_node) if name_node else "?"
            kind = "class" if t == "class_declaration" else "function"
            if t == "method_definition":
                kind = "method"
            sid = _sid(path, kind, name, node.start_point[0] + 1)
            out.append(
                {
                    "id": sid,
                    "kind": kind,
                    "name": name,
                    "path": path,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "parent_id": parent_id,
                    "extras": {"lang": "javascript"},
                }
            )
            for ch in node.children:
                walk(ch, parent_id=sid)
            return
        # arrow functions assigned: const x = () => {}
        if t == "variable_declarator":
            name_node = node.child_by_field_name("name")
            val = node.child_by_field_name("value")
            if name_node and val is not None and val.type in {"arrow_function", "function"}:
                name = text(name_node)
                sid = _sid(path, "function", name, node.start_point[0] + 1)
                out.append(
                    {
                        "id": sid,
                        "kind": "function",
                        "name": name,
                        "path": path,
                        "start_line": node.start_point[0] + 1,
                        "end_line": node.end_point[0] + 1,
                        "parent_id": parent_id,
                        "extras": {"lang": "javascript"},
                    }
                )
        for ch in node.children:
            walk(ch, parent_id=parent_id)

    walk(root)
    return out




def _walk_generic_names(source: bytes, path: str, lang_name: str, language: Language | None) -> list[dict[str, Any]]:
    """Generic Tree-sitter symbol walk for TS/Go/Java/Rust/C/C++."""
    if language is None:
        return []
    parser = Parser(language)
    tree = parser.parse(source)
    root = tree.root_node
    out: list[dict[str, Any]] = []
    mod_id = _sid(path, "module", Path(path).stem, 1)
    out.append(
        {
            "id": mod_id,
            "kind": "module",
            "name": Path(path).stem,
            "path": path,
            "start_line": 1,
            "end_line": source.count(b"\n") + 1,
            "parent_id": None,
            "extras": {"lang": lang_name},
        }
    )
    interesting = {
        "function_declaration", "function_definition", "method_declaration",
        "method_definition", "class_declaration", "class_definition",
        "struct_item", "impl_item", "interface_declaration", "type_declaration",
        "function_item", "mod_item",
    }

    def text(n) -> str:
        return source[n.start_byte : n.end_byte].decode("utf-8", errors="replace")

    def walk(node, parent_id: str = mod_id) -> None:
        t = node.type
        if t in interesting:
            name_node = node.child_by_field_name("name")
            name = text(name_node) if name_node else t
            kind = "class" if "class" in t or "struct" in t or "interface" in t else "function"
            if "method" in t:
                kind = "method"
            sid = _sid(path, kind, name, node.start_point[0] + 1)
            out.append(
                {
                    "id": sid,
                    "kind": kind,
                    "name": name[:200],
                    "path": path,
                    "start_line": node.start_point[0] + 1,
                    "end_line": node.end_point[0] + 1,
                    "parent_id": parent_id,
                    "extras": {"lang": lang_name, "node_type": t},
                }
            )
            for ch in node.children:
                walk(ch, parent_id=sid)
            return
        for ch in node.children:
            walk(ch, parent_id=parent_id)

    walk(root)
    return out

def index_repo_multi(root: str | Path, *, max_files: int = 3000) -> dict[str, Any]:
    root_p = Path(root).resolve()
    symbols: list[dict[str, Any]] = []
    files = 0
    by_lang: dict[str, int] = {}
    errors: list[str] = []
    for p in root_p.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _SKIP for part in p.parts):
            continue
        ext = p.suffix.lower()
        if ext not in _LANG_BY_EXT:
            continue
        lang, _lang_obj = _LANG_BY_EXT[ext]
        if lang == "javascript" and _JS_LANG is None:
            continue
        if files >= max_files:
            break
        rel = p.relative_to(root_p).as_posix()
        try:
            data = p.read_bytes()
            if len(data) > 1_500_000:
                errors.append(f"skip_large:{rel}")
                continue
            if lang == "python":
                syms = _extract_python(rel, data)
            elif lang == "javascript":
                syms = _walk_js_names(data, rel)
            else:
                _lang_obj = _LANG_BY_EXT.get(ext, (None, None))[1]
                syms = _walk_generic_names(data, rel, lang, _lang_obj)
            symbols.extend(syms)
            files += 1
            by_lang[lang] = by_lang.get(lang, 0) + 1
        except Exception as exc:
            errors.append(f"{rel}:{type(exc).__name__}")
    return {
        "root": str(root_p),
        "files_indexed": files,
        "symbol_count": len(symbols),
        "symbols": symbols,
        "by_lang": by_lang,
        "errors": errors[:50],
        "engine": "tree-sitter-multi",
        "product_scope": ["bots", "discord", "whatsapp", "telegram", "web", "apps"],
    }


__all__ = ["index_repo_multi"]
