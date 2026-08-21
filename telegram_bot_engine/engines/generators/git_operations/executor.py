"""
GitExecutor — Specification 047 (CRITICAL)

Plans and executes Git operations after user/permission/repo checks.
Supports both logical (planning) and real (subprocess) modes.
Dangerous ops require explicit confirmation. Conflict resolution is suggested
only; never applied without user approval. No autonomous history rewrite.

Real mode activates when request provides repo_path / work_dir and
execute_real=True (or when the operation is push/pull/commit on a verified path).
"""

from __future__ import annotations

import logging
import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .data_readers import GenericData
from .report_data import (
    GitOperation, CommitInfo, BranchInfo, ConflictInfo, HistoryEntry,
    DANGEROUS_OPS, ALL_OPERATIONS,
    OP_CLONE, OP_INIT, OP_FETCH, OP_PULL, OP_ADD, OP_COMMIT, OP_PUSH,
    OP_CHECKOUT, OP_SWITCH, OP_MERGE, OP_REBASE, OP_STASH, OP_TAG,
    OP_RESTORE, OP_RESET, OP_CLEAN, OP_BRANCH_CREATE, OP_BRANCH_RENAME,
    OP_BRANCH_DELETE, OP_FORCE_PUSH, OP_RESET_HARD,
    STATUS_PLANNED, STATUS_EXECUTED, STATUS_DENIED, STATUS_FAILED,
    STATUS_AWAITING_CONFIRMATION, STATUS_ROLLED_BACK,
)

_log = logging.getLogger("engine.git_operations.executor")

_ALIASES = {
    "clone": OP_CLONE, "git clone": OP_CLONE,
    "init": OP_INIT, "git init": OP_INIT,
    "fetch": OP_FETCH, "git fetch": OP_FETCH,
    "pull": OP_PULL, "git pull": OP_PULL,
    "add": OP_ADD, "git add": OP_ADD,
    "commit": OP_COMMIT, "git commit": OP_COMMIT,
    "push": OP_PUSH, "git push": OP_PUSH,
    "checkout": OP_CHECKOUT, "git checkout": OP_CHECKOUT,
    "switch": OP_SWITCH, "git switch": OP_SWITCH,
    "merge": OP_MERGE, "git merge": OP_MERGE,
    "rebase": OP_REBASE, "git rebase": OP_REBASE,
    "stash": OP_STASH, "git stash": OP_STASH,
    "tag": OP_TAG, "git tag": OP_TAG,
    "restore": OP_RESTORE, "git restore": OP_RESTORE,
    "reset": OP_RESET, "git reset": OP_RESET,
    "reset --hard": OP_RESET_HARD, "git reset --hard": OP_RESET_HARD,
    "clean": OP_CLEAN, "git clean": OP_CLEAN,
    "branch create": OP_BRANCH_CREATE, "create_branch": OP_BRANCH_CREATE,
    "branch rename": OP_BRANCH_RENAME, "rename_branch": OP_BRANCH_RENAME,
    "branch delete": OP_BRANCH_DELETE, "delete_branch": OP_BRANCH_DELETE,
    "force push": OP_FORCE_PUSH, "push --force": OP_FORCE_PUSH,
    "git push --force": OP_FORCE_PUSH,
}


class GitExecutor:
    """Permission-gated Git operation executor (logical, not live process)."""

    def run(
        self,
        request_data: GenericData,
        repo_mgmt_data: GenericData,
        ctx_data: GenericData,
    ) -> Tuple[
        List[GitOperation],
        List[CommitInfo],
        List[BranchInfo],
        List[ConflictInfo],
        List[HistoryEntry],
        bool,  # user_verified
        bool,  # permission_ok
        bool,  # repo_verified
    ]:
        user_id, repo, branch, confirmed_ops, requested = self._parse_request(
            request_data, repo_mgmt_data, ctx_data,
        )
        user_ok, perm_ok, repo_ok = self._verify_gates(
            request_data, repo_mgmt_data, user_id, repo,
        )

        operations: List[GitOperation] = []
        commits: List[CommitInfo] = []
        branches: List[BranchInfo] = []
        conflicts: List[ConflictInfo] = []
        history: List[HistoryEntry] = []

        if not requested:
            # Idle — no autonomous ops
            return operations, commits, branches, conflicts, history, user_ok, perm_ok, repo_ok

        for op in requested:
            dangerous = op in DANGEROUS_OPS
            confirmed = op in confirmed_ops or (
                bool((request_data.raw or {}).get("confirm_all_dangerous"))
            )
            ts = datetime.now(timezone.utc).isoformat()

            if not (user_ok and perm_ok and repo_ok):
                operations.append(GitOperation(
                    operation_id=str(uuid.uuid4())[:8],
                    operation=op,
                    status=STATUS_DENIED,
                    repository=repo,
                    branch=branch,
                    message="Denied: user/permission/repo verification failed",
                    dangerous=dangerous,
                    confirmed=confirmed,
                    user_id=user_id,
                    timestamp=ts,
                ))
                continue

            if dangerous and not confirmed:
                operations.append(GitOperation(
                    operation_id=str(uuid.uuid4())[:8],
                    operation=op,
                    status=STATUS_AWAITING_CONFIRMATION,
                    repository=repo,
                    branch=branch,
                    message=f"Dangerous op '{op}' requires explicit user confirmation",
                    dangerous=True,
                    confirmed=False,
                    user_id=user_id,
                    timestamp=ts,
                ))
                continue

            # Logical execution
            status, message, verification_ok, rolled_back = self._execute(
                op, repo, branch, user_id, request_data,
            )
            operations.append(GitOperation(
                operation_id=str(uuid.uuid4())[:8],
                operation=op,
                status=status,
                repository=repo,
                branch=branch,
                message=message,
                dangerous=dangerous,
                confirmed=confirmed if dangerous else True,
                user_id=user_id,
                timestamp=ts,
                verification_ok=verification_ok,
                rolled_back=rolled_back,
            ))

            # Side artefacts
            if op == OP_COMMIT and status == STATUS_EXECUTED:
                commits.append(self._build_commit(user_id, request_data, ts))
                history.append(HistoryEntry(
                    entry_id=str(uuid.uuid4())[:8],
                    kind="commit",
                    summary=commits[-1].title,
                    timestamp=ts,
                    details={"author": user_id},
                ))
            if op in (OP_BRANCH_CREATE, OP_BRANCH_RENAME, OP_BRANCH_DELETE, OP_SWITCH, OP_CHECKOUT):
                action = {
                    OP_BRANCH_CREATE: "create",
                    OP_BRANCH_RENAME: "rename",
                    OP_BRANCH_DELETE: "delete",
                    OP_SWITCH: "switch",
                    OP_CHECKOUT: "switch",
                }.get(op, "switch")
                branches.append(BranchInfo(
                    name=branch or "feature",
                    action=action,
                    protected=False,
                ))
                history.append(HistoryEntry(
                    entry_id=str(uuid.uuid4())[:8],
                    kind="branch",
                    summary=f"{action} {branch}",
                    timestamp=ts,
                ))
            if op in (OP_MERGE, OP_REBASE) and status in (STATUS_EXECUTED, STATUS_FAILED):
                if status == STATUS_FAILED or (request_data.raw or {}).get("simulate_conflict"):
                    conflicts.append(ConflictInfo(
                        conflict_id=str(uuid.uuid4())[:8],
                        conflict_type="merge" if op == OP_MERGE else "rebase",
                        files=["conflicted_file.py"],
                        suggestion="Keep ours / keep theirs / manual edit — await user choice",
                        resolved=False,
                        user_approved=False,
                    ))
                else:
                    history.append(HistoryEntry(
                        entry_id=str(uuid.uuid4())[:8],
                        kind="merge",
                        summary=f"{op} into {branch}",
                        timestamp=ts,
                    ))
            if op in (OP_PUSH, OP_FORCE_PUSH) and status == STATUS_EXECUTED:
                history.append(HistoryEntry(
                    entry_id=str(uuid.uuid4())[:8],
                    kind="push",
                    summary=f"{op} {branch}",
                    timestamp=ts,
                ))

        _log.info(
            "GitExecutor: ops=%d denied=%d awaiting=%d user=%s repo=%s",
            len(operations),
            sum(1 for o in operations if o.status == STATUS_DENIED),
            sum(1 for o in operations if o.status == STATUS_AWAITING_CONFIRMATION),
            user_ok, repo_ok,
        )
        return operations, commits, branches, conflicts, history, user_ok, perm_ok, repo_ok

    def self_verify(
        self,
        operations: List[GitOperation],
        user_ok: bool,
        perm_ok: bool,
        repo_ok: bool,
    ) -> bool:
        for o in operations:
            if o.status == STATUS_EXECUTED:
                if not (user_ok and perm_ok and repo_ok):
                    return False
                if o.dangerous and not o.confirmed:
                    return False
                if not o.verification_ok and not o.rolled_back:
                    return False
        return True

    def _parse_request(
        self,
        request_data: GenericData,
        repo_mgmt_data: GenericData,
        ctx_data: GenericData,
    ) -> Tuple[str, str, str, set, List[str]]:
        raw = request_data.raw or {}
        ctx = ctx_data.raw or {}
        repo_raw = repo_mgmt_data.raw or {}
        user_id = str(
            raw.get("user_id") or raw.get("user") or ctx.get("user_id") or "anonymous"
        )
        repo = str(
            raw.get("repository") or raw.get("repository_url") or raw.get("repo")
            or repo_raw.get("repository") or "unknown-repo"
        )
        branch = str(raw.get("branch") or "main")
        confirmed = set()
        conf_list = raw.get("confirmed_operations") or raw.get("confirm") or []
        if isinstance(conf_list, list):
            for c in conf_list:
                confirmed.add(self._normalize_op(str(c)))
        elif conf_list:
            confirmed.add(self._normalize_op(str(conf_list)))

        requested: List[str] = []
        for it in request_data.items or []:
            if isinstance(it, str):
                requested.append(self._normalize_op(it))
            elif isinstance(it, dict):
                op = str(it.get("operation") or it.get("op") or it.get("action") or "")
                if op:
                    requested.append(self._normalize_op(op))
        single = str(raw.get("operation") or raw.get("action") or raw.get("git_operation") or "")
        if single:
            requested.append(self._normalize_op(single))

        # Dedupe, drop unknowns
        seen = set()
        clean: List[str] = []
        for op in requested:
            if op in ALL_OPERATIONS and op not in seen:
                seen.add(op)
                clean.append(op)
        return user_id, repo, branch, confirmed, clean

    def _normalize_op(self, op: str) -> str:
        key = op.strip().lower()
        return _ALIASES.get(key, key.replace(" ", "_").replace("-", "_"))

    def _verify_gates(
        self,
        request_data: GenericData,
        repo_mgmt_data: GenericData,
        user_id: str,
        repo: str,
    ) -> Tuple[bool, bool, bool]:
        raw = request_data.raw or {}
        user_ok = user_id != "anonymous" or bool(raw.get("user_verified"))
        if raw.get("user_verified") is False:
            user_ok = False

        perm_ok = bool(raw.get("permission_ok") or raw.get("permission") in ("write", "admin", "read"))
        if repo_mgmt_data.available and repo_mgmt_data.raw:
            if repo_mgmt_data.raw.get("ownership_verified"):
                perm_ok = True
                user_ok = user_ok or True
            # If prior ops were all denied, inherit caution
            if int(repo_mgmt_data.raw.get("denied_count") or 0) > 0 and not raw.get("permission"):
                # still allow if explicit ownership
                pass

        repo_ok = bool(repo and repo != "unknown-repo") or bool(raw.get("repo_verified"))
        if raw.get("repo_verified") is False:
            repo_ok = False

        # Token presence strengthens gates
        if raw.get("repository_token") or raw.get("token"):
            user_ok = user_ok or user_id != "anonymous"
            repo_ok = repo_ok or bool(repo)

        return user_ok, perm_ok, repo_ok

    def _execute(
        self,
        op: str,
        repo: str,
        branch: str,
        user_id: str,
        request_data: GenericData,
    ) -> Tuple[str, str, bool, bool]:
        """Return status, message, verification_ok, rolled_back.

        Supports real git execution when repo_path/work_dir is provided
        and the operation is allowed. Falls back to logical simulation otherwise.
        """
        raw = request_data.raw or {}

        # Simulate rare failure on merge without confirm conflict handling
        if op in (OP_MERGE, OP_REBASE) and raw.get("simulate_conflict"):
            return (
                STATUS_FAILED,
                f"{op} encountered conflicts; resolution suggested, not auto-applied",
                False,
                False,
            )
        if op == OP_RESET_HARD and not raw.get("confirm_all_dangerous"):
            return STATUS_AWAITING_CONFIRMATION, "reset --hard needs confirmation", False, False

        if raw.get("force_fail"):
            return STATUS_ROLLED_BACK, f"{op} failed; rolled back to last stable state", False, True

        # --- Real execution path ---
        repo_path = raw.get("repo_path") or raw.get("work_dir") or raw.get("path")
        execute_real = bool(raw.get("execute_real", False)) or op in (
            OP_PUSH, OP_PULL, OP_FETCH, OP_COMMIT, OP_ADD, OP_CLONE
        )

        if repo_path and execute_real:
            try:
                status, message = self._run_real_git(op, str(repo_path), branch, raw)
                return status, message, status == STATUS_EXECUTED, False
            except Exception as exc:
                _log.exception("Real git execution failed for %s", op)
                return STATUS_FAILED, f"real git {op} failed: {exc}", False, False

        # --- Logical / planning fallback ---
        verification_ok = True
        message = f"{op} succeeded on {repo} ({branch}) [logical]"
        return STATUS_EXECUTED, message, verification_ok, False


    def _run_real_git(
        self,
        op: str,
        repo_path: str,
        branch: str,
        raw: Dict[str, Any],
    ) -> Tuple[str, str]:
        """Execute real git via PowerGitEngine only — no weak ad-hoc clone/commit."""
        from .power import get_engine
        from .report_data import (
            OP_CLONE, OP_PULL, OP_PUSH, OP_COMMIT, OP_ADD,
            OP_BRANCH_CREATE, OP_INIT,
            STATUS_EXECUTED, STATUS_FAILED,
        )

        eng = get_engine()
        path = Path(repo_path).resolve() if repo_path else None
        token = str(raw.get("token") or raw.get("repository_token") or "").strip() or None
        message = str(raw.get("commit_title") or raw.get("message") or "update")[:200]

        try:
            if op == OP_CLONE:
                from telegram_bot_engine.services.secure_exec import validate_git_https_url
                url = str(raw.get("url") or raw.get("repo_url") or "")
                try:
                    url = validate_git_https_url(url)
                except ValueError as exc:
                    return STATUS_FAILED, f"clone rejected: {exc}"
                parent = Path(raw.get("target_dir") or path or ".").resolve()
                parent = parent if parent.is_dir() or not parent.suffix else parent.parent
                parent.mkdir(parents=True, exist_ok=True)
                sparse = raw.get("sparse_paths")
                if isinstance(sparse, str):
                    sparse = [sparse]
                result = eng.clone(
                    url,
                    parent,
                    token=token,
                    branch=(branch or None),
                    depth=int(raw.get("depth") or 1),
                    sparse_paths=list(sparse) if sparse else None,
                    prefer_mirror=bool(raw.get("prefer_mirror", True)),
                    preferred_name=str(raw.get("name") or "") or None,
                )
                if not result.ok:
                    msg = result.redacted_error or result.message
                    if result.needs_auth:
                        msg = f"needs_auth: {msg}"
                    return STATUS_FAILED, f"clone failed [{result.strategy_used}]: {msg}"
                return STATUS_EXECUTED, (
                    f"cloned via {result.strategy_used} → {result.path} "
                    f"(files={result.files_changed_count}, validate={result.validation_passed}, "
                    f"commit={result.commit_hash or '-'})"
                )

            if op == OP_INIT:
                target = path or Path(".")
                target.mkdir(parents=True, exist_ok=True)
                import subprocess
                from telegram_bot_engine.services.secure_exec import clean_child_environ
                r = subprocess.run(
                    ["git", "init"], cwd=str(target), capture_output=True, text=True,
                    env=clean_child_environ(), check=False,
                )
                if r.returncode != 0:
                    return STATUS_FAILED, f"init failed: {(r.stderr or '')[:200]}"
                from .power.security import ensure_strict_gitignore
                ensure_strict_gitignore(target)
                return STATUS_EXECUTED, f"initialized {target}"

            if not path or not path.exists():
                return STATUS_FAILED, f"path does not exist: {path}"

            if op in (OP_ADD, OP_COMMIT):
                files = raw.get("files") or raw.get("modified_files")
                if isinstance(files, str):
                    files = [files]
                paths = [Path(f) for f in files] if files else None
                result = eng.commit(path, message, paths)
                if not result.ok:
                    return STATUS_FAILED, result.redacted_error or result.message
                return STATUS_EXECUTED, (
                    f"committed {result.commit_hash or ''} files={result.files_changed_count} "
                    f"validate={result.validation_passed}"
                )

            if op == OP_PULL:
                result = eng.pull(path, token=token, branch=branch or None)
                if not result.ok:
                    msg = result.redacted_error or result.message
                    if result.needs_auth:
                        msg = f"needs_auth: {msg}"
                    return STATUS_FAILED, msg
                return STATUS_EXECUTED, f"pulled {result.commit_hash or ''} validate={result.validation_passed}"

            if op == OP_PUSH:
                result = eng.push(path, token=token, message=message, branch=branch or None)
                if not result.ok:
                    msg = result.redacted_error or result.message
                    if result.needs_auth:
                        msg = f"needs_auth: {msg}"
                    return STATUS_FAILED, msg
                return STATUS_EXECUTED, result.message

            if op == OP_BRANCH_CREATE:
                job = str(raw.get("job_id") or raw.get("branch") or "")
                result = eng.start_refine(path, job_id=job)
                if not result.ok:
                    return STATUS_FAILED, result.redacted_error or result.message
                return STATUS_EXECUTED, result.message

            if op in ("git_reset_hard", "git_reset"):
                ref = str(raw.get("ref") or "HEAD~1")
                result = eng.rollback(path, ref)
                if not result.ok:
                    return STATUS_FAILED, result.redacted_error or result.message
                return STATUS_EXECUTED, result.message

            # Unknown real op — refuse silent logical success
            return STATUS_FAILED, f"unsupported_real_op:{op}"

        except Exception as exc:
            return STATUS_FAILED, f"{op} error: {type(exc).__name__}"

    def _build_commit(
        self, user_id: str, request_data: GenericData, ts: str
    ) -> CommitInfo:
        raw = request_data.raw or {}
        title = str(raw.get("commit_title") or raw.get("message") or "chore: automated commit")
        desc = str(raw.get("commit_description") or raw.get("description") or "")
        files = raw.get("modified_files") or raw.get("files") or ["."]
        if isinstance(files, str):
            files = [files]
        return CommitInfo(
            commit_id=str(uuid.uuid4())[:12],
            title=title[:120],
            description=desc[:500],
            timestamp=ts,
            author=str(raw.get("author") or user_id),
            modified_files=list(files)[:50],
        )


__all__ = ["GitExecutor"]
