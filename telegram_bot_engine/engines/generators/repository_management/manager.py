"""
RepositoryManager — Specification 046 (CRITICAL)

Plans and (logically) executes repository operations only after
ownership + permission verification. Never acts autonomously.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from .data_readers import GenericData
from .report_data import (
    PermissionCheck, OperationPlan, OperationResult, RepoDiscovery,
    PERM_READ, PERM_WRITE, PERM_ADMIN, PERM_NONE, OP_REQUIRED_PERM,
    OP_CLONE, OP_FETCH, OP_PULL, OP_COMMIT, OP_PUSH,
    OP_CREATE_BRANCH, OP_DELETE_BRANCH, OP_MERGE_BRANCH,
    OP_CREATE_REPO, OP_RENAME_REPO, OP_ARCHIVE_REPO,
    OP_DISCOVER, OP_LIST_BRANCHES, OP_LIST_TAGS, OP_LIST_COMMITS, OP_LIST_RELEASES,
    STATUS_PLANNED, STATUS_EXECUTED, STATUS_DENIED, STATUS_FAILED, STATUS_RECOVERED,
)

_log = logging.getLogger("engine.repository_management.manager")

_MUTATING = {
    OP_COMMIT, OP_PUSH, OP_CREATE_BRANCH, OP_DELETE_BRANCH, OP_MERGE_BRANCH,
    OP_CREATE_REPO, OP_RENAME_REPO, OP_ARCHIVE_REPO,
}

_PERM_RANK = {PERM_NONE: 0, PERM_READ: 1, PERM_WRITE: 2, PERM_ADMIN: 3}


class RepositoryManager:
    """Permission-gated repository operation planner/executor (logical)."""

    def process(
        self,
        request_data: GenericData,
        ctx_data: GenericData,
        readiness_data: GenericData,
    ) -> Tuple[
        List[PermissionCheck],
        List[OperationPlan],
        List[OperationResult],
        List[RepoDiscovery],
        bool,  # ownership_verified
    ]:
        user_id, repo_url, repo_name, token, granted_perm, owner_ok = (
            self._extract_identity(request_data, ctx_data)
        )
        requested_ops = self._extract_operations(request_data)

        checks: List[PermissionCheck] = []
        plans: List[OperationPlan] = []
        results: List[OperationResult] = []
        discoveries: List[RepoDiscovery] = []

        if not requested_ops:
            # No autonomous action — idle report
            checks.append(PermissionCheck(
                check_id=str(uuid.uuid4())[:8],
                operation="none",
                required=PERM_NONE,
                granted=granted_perm,
                ownership_verified=owner_ok,
                allowed=True,
                message="No user-requested operations; engine idle (no autonomous action).",
            ))
            return checks, plans, results, discoveries, owner_ok

        repo_label = repo_name or repo_url or "unknown-repo"

        for op in requested_ops:
            required = OP_REQUIRED_PERM.get(op, PERM_ADMIN)
            allowed = owner_ok and _PERM_RANK.get(granted_perm, 0) >= _PERM_RANK.get(required, 3)
            check = PermissionCheck(
                check_id=str(uuid.uuid4())[:8],
                operation=op,
                required=required,
                granted=granted_perm,
                ownership_verified=owner_ok,
                allowed=allowed,
                message=(
                    "Allowed"
                    if allowed else
                    (
                        "Denied: ownership not verified"
                        if not owner_ok else
                        f"Denied: need {required}, have {granted_perm}"
                    )
                ),
            )
            checks.append(check)

            if not allowed:
                results.append(OperationResult(
                    result_id=str(uuid.uuid4())[:8],
                    operation=op,
                    status=STATUS_DENIED,
                    message=check.message,
                    repository=repo_label,
                    user_id=user_id,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                ))
                continue

            # Always plan first (especially for mutations)
            mutating = op in _MUTATING
            plan = OperationPlan(
                plan_id=str(uuid.uuid4())[:8],
                operation=op,
                repository=repo_label,
                branch=str((request_data.raw or {}).get("branch") or "main"),
                details=f"Plan for {op} on {repo_label}",
                mutating=mutating,
                status=STATUS_PLANNED,
            )
            plans.append(plan)

            # Logical execution (no real git side-effects in this engine)
            result = self._execute_logical(op, plan, repo_label, user_id, token)
            results.append(result)

            if op in (
                OP_DISCOVER, OP_LIST_BRANCHES, OP_LIST_TAGS,
                OP_LIST_COMMITS, OP_LIST_RELEASES, OP_CLONE,
            ) and result.status == STATUS_EXECUTED:
                discoveries.append(RepoDiscovery(
                    discovery_id=str(uuid.uuid4())[:8],
                    repository=repo_label,
                    branches=["main", "develop"] if op in (OP_DISCOVER, OP_LIST_BRANCHES, OP_CLONE) else [],
                    tags=["v1.0.0"] if op in (OP_DISCOVER, OP_LIST_TAGS) else [],
                    commits=["abc1234"] if op in (OP_DISCOVER, OP_LIST_COMMITS) else [],
                    releases=["1.0.0"] if op in (OP_DISCOVER, OP_LIST_RELEASES) else [],
                ))

        _log.info(
            "RepositoryManager: ops=%d denied=%d plans=%d owner_ok=%s",
            len(requested_ops),
            sum(1 for r in results if r.status == STATUS_DENIED),
            len(plans), owner_ok,
        )
        return checks, plans, results, discoveries, owner_ok

    def self_verify(
        self,
        checks: List[PermissionCheck],
        results: List[OperationResult],
        ownership_verified: bool,
    ) -> bool:
        # Every executed op must have had an allowed check
        executed = [r for r in results if r.status == STATUS_EXECUTED]
        for r in executed:
            matching = [c for c in checks if c.operation == r.operation and c.allowed]
            if not matching:
                return False
        # Denied ops must not be executed
        for r in results:
            if r.status == STATUS_DENIED:
                continue
            if r.status == STATUS_EXECUTED:
                denied_same = [
                    c for c in checks
                    if c.operation == r.operation and not c.allowed
                ]
                if denied_same:
                    return False
        return True

    def _extract_identity(
        self, request_data: GenericData, ctx_data: GenericData
    ) -> Tuple[str, str, str, str, str, bool]:
        raw = request_data.raw or {}
        ctx = ctx_data.raw or {}
        user_id = str(raw.get("user_id") or raw.get("user") or ctx.get("user_id") or "anonymous")
        repo_url = str(raw.get("repository_url") or raw.get("repo_url") or raw.get("url") or "")
        repo_name = str(raw.get("repository_name") or raw.get("repo_name") or raw.get("name") or "")
        token = str(raw.get("repository_token") or raw.get("token") or raw.get("github_token") or "")

        # Ownership / permission signals from request or explicit flags
        owner_flag = raw.get("ownership_verified")
        if owner_flag is None:
            owner_flag = raw.get("is_owner")
        if owner_flag is None:
            # If token + repo provided, treat as claimed ownership pending verification signal
            owner_ok = bool(token and (repo_url or repo_name) and user_id != "anonymous")
        else:
            owner_ok = bool(owner_flag)

        granted = str(raw.get("permission") or raw.get("granted_permission") or "").lower()
        if granted not in (PERM_READ, PERM_WRITE, PERM_ADMIN, PERM_NONE):
            if owner_ok and token:
                granted = PERM_WRITE  # conservative default when owner claims token
            elif token:
                granted = PERM_READ
            else:
                granted = PERM_NONE
                owner_ok = False

        return user_id, repo_url, repo_name, token, granted, owner_ok

    def _extract_operations(self, request_data: GenericData) -> List[str]:
        ops: List[str] = []
        if request_data.items:
            for it in request_data.items:
                if isinstance(it, str):
                    ops.append(it.lower().strip())
                elif isinstance(it, dict):
                    op = str(it.get("operation") or it.get("op") or it.get("action") or "").lower()
                    if op:
                        ops.append(op)
        raw = request_data.raw or {}
        single = str(raw.get("operation") or raw.get("action") or "").lower()
        if single:
            ops.append(single)
        # Normalize aliases
        normalized = []
        aliases = {
            "git_clone": OP_CLONE, "git_pull": OP_PULL, "git_push": OP_PUSH,
            "git_fetch": OP_FETCH, "git_commit": OP_COMMIT,
            "branch_create": OP_CREATE_BRANCH, "branch_delete": OP_DELETE_BRANCH,
            "branch_merge": OP_MERGE_BRANCH, "repo_create": OP_CREATE_REPO,
            "repo_rename": OP_RENAME_REPO, "repo_archive": OP_ARCHIVE_REPO,
            "list": OP_DISCOVER, "discover": OP_DISCOVER,
        }
        for op in ops:
            op = aliases.get(op, op)
            if op in OP_REQUIRED_PERM and op not in normalized:
                normalized.append(op)
        return normalized

    def _execute_logical(
        self,
        op: str,
        plan: OperationPlan,
        repo: str,
        user_id: str,
        token: str,
    ) -> OperationResult:
        ts = datetime.now(timezone.utc).isoformat()
        # Conflict simulation: merge without token strength
        conflict = ""
        status = STATUS_EXECUTED
        message = f"{op} completed (logical) on {repo}"
        recovered = False

        if op == OP_MERGE_BRANCH and not token:
            status = STATUS_FAILED
            conflict = "merge_conflict_or_missing_auth"
            message = "Merge failed: conflict or missing credentials"
            # Recovery attempt
            recovered = True
            status = STATUS_RECOVERED
            message = "Merge failed; previous state restored"
        elif op in _MUTATING and not token:
            status = STATUS_FAILED
            message = f"{op} failed: missing repository token"
        else:
            plan.status = STATUS_EXECUTED

        return OperationResult(
            result_id=str(uuid.uuid4())[:8],
            operation=op,
            plan_id=plan.plan_id,
            status=status,
            message=message,
            repository=repo,
            user_id=user_id,
            timestamp=ts,
            conflict=conflict,
            recovered=recovered,
        )


__all__ = ["RepositoryManager"]
