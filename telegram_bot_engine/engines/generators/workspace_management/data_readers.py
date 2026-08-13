"""Tolerant data readers for Workspace Management (Spec 049)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..common.tolerant_readers import GenericData, BaseReader as _BaseReader, _safe
from ....core.context import GenerationContext


class FileSystemReader(_BaseReader):
    ARTEFACT_KEY = "file_system_report"
    LIST_KEY = "operations"


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
    LIST_KEY = "actions"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("workspace_request")
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            acts = raw.get("actions") or raw.get("workspace_actions") or raw.get("operations") or []
            if isinstance(acts, list):
                d.items = acts
            elif acts:
                d.items = [acts]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "FileSystemReader",
    "GitOperationsReader",
    "RepositoryManagementReader",
    "ProjectContextReader",
    "UserRequestReader",
]
