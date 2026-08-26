"""Phase C — Codebase Intelligence (Tree-sitter + Jedi + hybrid retrieval + blast radius)."""
from __future__ import annotations

from .blast_radius import blast_radius
from .preflight import analyze_edit_preflight
from .hybrid_retrieval import hybrid_search
from .persistent_index import build_and_save_index, get_or_build_graph, load_index
from .symbol_graph import build_symbol_graph
from .tree_sitter_index import index_python_repo, parse_python_source

try:
    from .jedi_analysis import find_references, goto_definition, names_in_module
except Exception:  # pragma: no cover
    find_references = None  # type: ignore
    goto_definition = None  # type: ignore
    names_in_module = None  # type: ignore

__all__ = [
    "index_python_repo",
    "parse_python_source",
    "build_symbol_graph",
    "hybrid_search",
    "blast_radius",
    "analyze_edit_preflight",
    "build_and_save_index",
    "get_or_build_graph",
    "load_index",
    "find_references",
    "goto_definition",
    "names_in_module",
]
