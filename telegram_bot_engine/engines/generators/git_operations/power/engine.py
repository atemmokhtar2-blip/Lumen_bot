"""
Power Git Engine — pure git operations facade.

No Telegram, no AI, no DB. Accepts abstract ops and returns GitEngineResult.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from .maintenance import prepare_dest_dir, unique_workdir, git_gc, gc_mirrors
from .result import GitEngineResult
from .security import assert_inside_sandbox, ensure_strict_gitignore, scan_files_for_secrets, redact_text
from .strategies import clone_multi_strategy
from .verify import structural_validate
from .workflow import (
    atomic_commit,
    create_ephemeral_branch,
    merge_ephemeral_to,
    rollback_hard,
    head_hash,
)


class PowerGitEngine:
    """Single entry for clone / commit / branch / rollback / validate / gc."""

    def clone(
        self,
        url: str,
        dest_parent: str | Path,
        *,
        token: Optional[str] = None,
        branch: Optional[str] = None,
        depth: int = 1,
        sparse_paths: Optional[list[str]] = None,
        prefer_mirror: bool = True,
        preferred_name: Optional[str] = None,
    ) -> GitEngineResult:
        parent = Path(dest_parent).expanduser().resolve()
        parent.mkdir(parents=True, exist_ok=True)
        name = preferred_name or "repo"
        dest = prepare_dest_dir(parent, name)
        result = clone_multi_strategy(
            url,
            dest,
            token=token,
            branch=branch,
            depth=depth,
            sparse_paths=sparse_paths,
            prefer_mirror=prefer_mirror,
        )
        if result.ok and result.path:
            ensure_strict_gitignore(Path(result.path))
        return result

    def validate(self, path: str | Path) -> GitEngineResult:
        root = Path(path)
        ok, details, err = structural_validate(root)
        return GitEngineResult(
            ok=ok,
            op="validate",
            validation_passed=ok,
            path=str(root),
            files_changed_count=int(details.get("file_count") or 0),
            commit_hash=head_hash(root),
            message="validation_ok" if ok else (err or "validation_failed"),
            redacted_error="" if ok else err,
            strategy_used="structural",
            metadata=details,
        )

    def commit(
        self,
        path: str | Path,
        message: str,
        files: Iterable[Path] | None = None,
    ) -> GitEngineResult:
        return atomic_commit(Path(path), files, message)

    def start_refine(self, path: str | Path, *, job_id: str = "") -> GitEngineResult:
        return create_ephemeral_branch(Path(path), job_id=job_id)

    def finish_refine(
        self,
        path: str | Path,
        branch: str,
        *,
        target: str = "main",
        merge: bool = True,
    ) -> GitEngineResult:
        if merge:
            return merge_ephemeral_to(Path(path), branch, target=target)
        return rollback_hard(Path(path), "HEAD")  # noop-ish fallback

    def rollback(self, path: str | Path, ref: str = "HEAD~1") -> GitEngineResult:
        return rollback_hard(Path(path), ref)

    def safe_path(self, sandbox: str | Path, relative: str | Path) -> Path:
        return assert_inside_sandbox(Path(relative), Path(sandbox))

    def new_workdir(self, parent: str | Path, *, prefix: str = "work") -> Path:
        return unique_workdir(Path(parent), prefix=prefix)

    def gc(self, path: str | Path) -> GitEngineResult:
        ok, msg = git_gc(Path(path))
        return GitEngineResult(ok=ok, op="gc", message=msg, path=str(path), strategy_used="git_gc")

    def gc_all_mirrors(self) -> GitEngineResult:
        stats = gc_mirrors()
        return GitEngineResult(ok=True, op="gc_mirrors", message="done", metadata=stats, strategy_used="git_gc")


# module-level singleton style API
_engine = PowerGitEngine()


def get_engine() -> PowerGitEngine:
    return _engine
