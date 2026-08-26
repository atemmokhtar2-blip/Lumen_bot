"""Phase C+ — global codebase intelligence for bots, apps, and web projects."""
from __future__ import annotations

from .blast_radius import blast_radius
from .hybrid_retrieval import hybrid_search
from .incremental import ensure_incremental_index
from .multi_lang import index_repo_multi
from .persistent_index import build_and_save_index, get_or_build_graph, load_index
from .postflight import analyze_edit_postflight
from .preflight import analyze_edit_preflight
from .symbol_graph import build_symbol_graph
from .tree_sitter_index import index_python_repo, parse_python_source
from .vector_store import CodeVectorStore, build_vector_index_from_symbols

try:
    from .jedi_analysis import find_references, goto_definition, names_in_module
except Exception:  # pragma: no cover
    find_references = None  # type: ignore
    goto_definition = None  # type: ignore
    names_in_module = None  # type: ignore

__all__ = [
    "index_python_repo",
    "parse_python_source",
    "index_repo_multi",
    "build_symbol_graph",
    "hybrid_search",
    "blast_radius",
    "build_and_save_index",
    "get_or_build_graph",
    "load_index",
    "ensure_incremental_index",
    "analyze_edit_preflight",
    "analyze_edit_postflight",
    "CodeVectorStore",
    "build_vector_index_from_symbols",
    "find_references",
    "goto_definition",
    "names_in_module",
]

try:
    from .repo_context import pack_repo_context_for_goal, context_to_agent_block
except Exception:  # pragma: no cover
    pack_repo_context_for_goal = None  # type: ignore
    context_to_agent_block = None  # type: ignore
