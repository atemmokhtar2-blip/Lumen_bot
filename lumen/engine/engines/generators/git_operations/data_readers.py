"""Tolerant data readers for Git Operations (Spec 047)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..common.tolerant_readers import GenericData, BaseReader as _BaseReader, _safe
from ....core.context import GenerationContext


class RepositoryManagementReader(_BaseReader):
    ARTEFACT_KEY = "repository_management_report"
    LIST_KEY = "results"


class ProjectContextReader(_BaseReader):
    ARTEFACT_KEY = "project_context_report"
    LIST_KEY = "contexts"


class ProductionReadinessReader(_BaseReader):
    ARTEFACT_KEY = "production_readiness_report"
    LIST_KEY = "axes"


class UserRequestReader(_BaseReader):
    ARTEFACT_KEY = "user_request"
    LIST_KEY = "operations"

    def read(self, ctx: GenerationContext) -> GenericData:
        d = GenericData()
        try:
            a = ctx.get(self.ARTEFACT_KEY)
            if a is None:
                a = ctx.get("git_request") or ctx.get("repository_request")
            if a is None and (ctx.get("git_operation") or ctx.get("operation") or ctx.get("repo_path")):
                # Dynamic fallback from artefacts set by formal → git link
                a = {
                    "operation": ctx.get("git_operation") or ctx.get("operation"),
                    "git_operation": ctx.get("git_operation") or ctx.get("operation"),
                    "repo_path": ctx.get("repo_path") or str(ctx.work_dir or ""),
                    "execute_real": ctx.get("execute_real", False),
                    "message": ctx.get("message") or "",
                    "operations": [ctx.get("git_operation") or ctx.get("operation")] if (ctx.get("git_operation") or ctx.get("operation")) else [],
                }
            if a is None and getattr(ctx, "request", None):
                a = {"text": ctx.request, "operation": "commit"}
            if a is None:
                d.error = "missing user_request"
                return d
            raw = _safe(a)
            d.raw, d.available = raw, True
            ops = raw.get("operations") or raw.get("git_operations") or []
            if isinstance(ops, list):
                d.items = ops
            elif ops:
                d.items = [ops]
        except Exception as e:
            d.error = str(e)
        return d


__all__ = [
    "GenericData",
    "RepositoryManagementReader",
    "ProjectContextReader",
    "ProductionReadinessReader",
    "UserRequestReader",
]
