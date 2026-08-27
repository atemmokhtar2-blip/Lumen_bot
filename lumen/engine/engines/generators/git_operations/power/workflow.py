"""Safe modification workflow: ephemeral branches, atomic commits, rollback."""
from __future__ import annotations

import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from typing import Iterable, Optional

from .result import GitEngineResult
from .security import ensure_strict_gitignore, scan_files_for_secrets, redact_text
from .verify import structural_validate, count_files


def _run(argv: list[str], cwd: Path, timeout: int = 120) -> tuple[int, str, str]:
    try:
        from lumen.engine.services.secure_exec import clean_child_environ
        env = clean_child_environ(extra={"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"})
    except Exception:
        env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        from lumen.engine.services.secure_exec import clean_child_environ
        env = clean_child_environ(extra={"GIT_TERMINAL_PROMPT": "0"})
    except Exception:
        pass
    try:
        p = subprocess.run(argv, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env, check=False)
        return int(p.returncode), p.stdout or "", p.stderr or ""
    except Exception as exc:
        return 1, "", type(exc).__name__


def head_hash(repo: Path) -> Optional[str]:
    code, out, _ = _run(["git", "rev-parse", "HEAD"], repo)
    return out.strip() if code == 0 else None


def create_ephemeral_branch(repo: Path, *, job_id: str = "") -> GitEngineResult:
    """Create ai-refine-{job}-{ts} branch from current HEAD. Never commits to main directly."""
    repo = Path(repo)
    if not (repo / ".git").exists():
        return GitEngineResult.fail("branch", message="not_a_git_repo", path=str(repo))
    base = head_hash(repo)
    jid = re.sub(r"[^a-zA-Z0-9_-]", "", (job_id or uuid.uuid4().hex[:8]))[:32]
    name = f"ai-refine-{jid}-{int(time.time())}"
    code, out, err = _run(["git", "checkout", "-b", name], repo)
    if code != 0:
        return GitEngineResult.fail(
            "branch",
            message="branch_create_failed",
            redacted_error=redact_text(err or out)[:200],
            path=str(repo),
        )
    return GitEngineResult(
        ok=True,
        op="branch",
        strategy_used="ephemeral_branch",
        path=str(repo),
        commit_hash=base,
        message=f"branch:{name}",
        metadata={"branch": name, "base_head": base},
        validation_passed=True,
    )


def atomic_commit(
    repo: Path,
    paths: Iterable[Path] | None,
    message: str,
    *,
    allow_empty: bool = False,
) -> GitEngineResult:
    """
    Stage paths (or all), secret-scan, ensure gitignore, single atomic commit.
    Fail-closed on secrets.
    """
    repo = Path(repo).resolve()
    ensure_strict_gitignore(repo)

    if paths:
        files = [Path(p) for p in paths]
        for f in files:
            rel = f if not f.is_absolute() else f
            _run(["git", "add", "--", str(rel.relative_to(repo) if rel.is_absolute() and str(rel).startswith(str(repo)) else rel)], repo)
    else:
        _run(["git", "add", "-A"], repo)

    code, out, _ = _run(["git", "status", "--porcelain"], repo)
    changed = [ln for ln in out.splitlines() if ln.strip()]
    if not changed and not allow_empty:
        return GitEngineResult(
            ok=True,
            op="commit",
            message="nothing_to_commit",
            path=str(repo),
            files_changed_count=0,
            validation_passed=True,
            strategy_used="atomic_commit",
        )

    # Collect staged file paths for secret scan
    code, out, _ = _run(["git", "diff", "--cached", "--name-only"], repo)
    staged = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            staged.append(repo / line)
    findings = scan_files_for_secrets(staged, root=repo)
    if findings:
        _run(["git", "reset", "HEAD"], repo)
        return GitEngineResult.fail(
            "commit",
            message="secret_scan_blocked",
            redacted_error=";".join(findings[:5]),
            path=str(repo),
            strategy_used="atomic_commit",
            metadata={"findings": findings[:10]},
        )

    msg = (message or "update").strip()[:200] or "update"
    code, out, err = _run(["git", "commit", "-m", msg], repo)
    if code != 0:
        return GitEngineResult.fail(
            "commit",
            message="commit_failed",
            redacted_error=redact_text(err or out)[:200],
            path=str(repo),
            strategy_used="atomic_commit",
        )
    h = head_hash(repo)
    ok, details, _ = structural_validate(repo)
    return GitEngineResult(
        ok=True,
        op="commit",
        strategy_used="atomic_commit",
        path=str(repo),
        commit_hash=h,
        files_changed_count=len(changed),
        validation_passed=ok,
        message="committed",
        metadata={"commit_message": msg, **details},
    )


def rollback_hard(repo: Path, target_ref: str = "HEAD~1") -> GitEngineResult:
    """Instant rollback to previous stable ref (default HEAD~1)."""
    repo = Path(repo)
    before = head_hash(repo)
    ref = target_ref if target_ref else "HEAD~1"
    # safety: only allow HEAD forms and full hashes
    if not re.match(r"^(HEAD(~[0-9]+)?|[a-f0-9]{7,40})$", ref):
        return GitEngineResult.fail("rollback", message="invalid_ref", path=str(repo))
    code, out, err = _run(["git", "reset", "--hard", ref], repo)
    if code != 0:
        return GitEngineResult.fail(
            "rollback",
            message="rollback_failed",
            redacted_error=redact_text(err or out)[:200],
            path=str(repo),
        )
    after = head_hash(repo)
    return GitEngineResult(
        ok=True,
        op="rollback",
        strategy_used="reset_hard",
        path=str(repo),
        commit_hash=after,
        message=f"rolled_back:{before}->{after}",
        validation_passed=True,
        metadata={"previous": before, "current": after, "ref": ref},
    )


def merge_ephemeral_to(repo: Path, branch: str, target: str = "main") -> GitEngineResult:
    """Merge ephemeral branch into target after successful validation."""
    repo = Path(repo)
    code, _, err = _run(["git", "checkout", target], repo)
    if code != 0:
        code, _, err = _run(["git", "checkout", "master"], repo)
        target = "master" if code == 0 else target
    if code != 0:
        return GitEngineResult.fail("merge", message="checkout_target_failed", redacted_error=redact_text(err)[:200], path=str(repo))
    code, out, err = _run(["git", "merge", "--no-ff", branch, "-m", f"merge {branch}"], repo)
    if code != 0:
        _run(["git", "merge", "--abort"], repo)
        return GitEngineResult.fail("merge", message="merge_failed", redacted_error=redact_text(err or out)[:200], path=str(repo))
    # delete ephemeral branch
    _run(["git", "branch", "-D", branch], repo)
    return GitEngineResult(
        ok=True,
        op="merge",
        strategy_used="merge_ephemeral",
        path=str(repo),
        commit_hash=head_hash(repo),
        message=f"merged:{branch}->{target}",
        validation_passed=True,
        metadata={"branch": branch, "target": target},
    )
