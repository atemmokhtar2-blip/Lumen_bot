"""Semantic memory package for Lumen_bot (Mem0-inspired).

Provides durable, per-user long-term memory with semantic retrieval so the
engine "remembers" each user and their projects across sessions — enabling
precise edits ("remove a button", "add a command") with full continuity.

Public API:
  - get_semantic_store(): SemanticMemoryStore (facts + vectors)
  - ingest_exchange(): extract facts from an exchange + apply ADD/UPDATE/DELETE/NOOP
  - recall() / build_memory_context() / memory_context_for_llm(): retrieval
  - get_project_memory_store(): ProjectMemoryStore (editable project cards)
"""
from .store import SemanticMemoryStore, MemoryRecord, get_semantic_store
from .extraction import extract_facts, ingest_exchange
from .retrieval import recall, build_memory_context, memory_context_for_llm
from .project_memory import (
    ProjectCard,
    ProjectMemoryStore,
    get_project_memory_store,
)

__all__ = [
    "SemanticMemoryStore",
    "MemoryRecord",
    "get_semantic_store",
    "extract_facts",
    "ingest_exchange",
    "recall",
    "build_memory_context",
    "memory_context_for_llm",
    "ProjectCard",
    "ProjectMemoryStore",
    "get_project_memory_store",
]
