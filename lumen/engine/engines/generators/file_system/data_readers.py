"""Tolerant data readers for File System Engine (Spec 048)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..common.tolerant_readers import GenericData, BaseReader as _BaseReader, _safe
from ....core.context import GenerationContext


class GitOperationsReader(_BaseReader):
    ARTEFACT_KEY = "git_operations_report"
    LIST_KEY = "operations"


class RepositoryManagementReader(_BaseReader):
    ARTEFACT_KEY = "repository_management_report"
    LIST_KEY = "results"


class ProjectContextReader(_BaseReader):
    ARTEFACT_KEY = "project_context_report"
    LIST_KEY = "contexts"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "operations"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("fs_request") or ctx.get("file_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            ops = raw.get("operations") or raw.get("file_operations") or []
            if isinstance(ops, list):
                d.items = ops
            elif ops:
                d.items = [ops]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "GitOperationsReader",
    "RepositoryManagementReader",
    "ProjectContextReader",
    "UserRequestReader",
]
