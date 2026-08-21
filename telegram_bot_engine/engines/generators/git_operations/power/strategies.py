"""Multi-strategy clone with circuit-breaker fallback chain."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import zipfile
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .mirror import ensure_bare_mirror, materialize_from_mirror
from .result import GitEngineResult
from .verify import structural_validate, count_files

logger = logging.getLogger(__name__)


def _run_git(argv: list[str], *, timeout: int = 300, token: Optional[str] = None) -> tuple[int, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    try:
        from telegram_bot_engine.services.secure_exec import clean_child_environ
        env = clean_child_environ(extra={"GIT_TERMINAL_PROMPT": "0"})
    except Exception:
        pass
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env, check=False)
        err = (proc.stderr or "") + (proc.stdout or "")
        try:
            from ..smart_clone import _redact
            err = _redact(err, token)
        except Exception:
            pass
        return int(proc.returncode), err
    except Exception as exc:
        return 1, f"{type(exc).__name__}"


def _auth_url(url: str, token: Optional[str]) -> str:
    from ..smart_clone import _inject_token
    return _inject_token(url, token) if token else url


def _is_auth(err: str, code: int) -> bool:
    from ..smart_clone import _is_auth_failure
    return _is_auth_failure(err, code)


def _finalize(dest: Path, *, op: str, strategy: str, url: str, attempts: int) -> GitEngineResult:
    ok_struct, details, err = structural_validate(dest)
    files = int(details.get("file_count") or count_files(dest))
    commit = None
    code, out = _run_git(["git", "-C", str(dest), "rev-parse", "HEAD"])
    if code == 0:
        commit = out.strip().splitlines()[-1][:40] if out.strip() else None
    if not ok_struct and files <= 0:
        return GitEngineResult.fail(
            op,
            message="verification_failed",
            redacted_error=err or "empty_or_invalid",
            strategy_used=strategy,
            attempts=attempts,
            url=url,
            path=str(dest),
            metadata=details,
        )
    return GitEngineResult(
        ok=True,
        op=op,
        strategy_used=strategy,
        files_changed_count=files,
        commit_hash=commit,
        validation_passed=ok_struct,
        path=str(dest),
        url=url,
        message="clone_ok" if ok_struct else "clone_ok_soft_validation",
        attempts=attempts,
        metadata=details,
    )


def strategy_local_mirror(
    url: str, dest: Path, *, token: Optional[str], branch: Optional[str], depth: int
) -> GitEngineResult:
    ok, mirror, msg = ensure_bare_mirror(url, token=token)
    if not ok:
        return GitEngineResult.fail("clone", message=msg, strategy_used="local_mirror", url=url)
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    ok2, msg2 = materialize_from_mirror(mirror, dest, branch=branch, depth=depth)
    if not ok2:
        return GitEngineResult.fail("clone", message=msg2, strategy_used="local_mirror", url=url)
    return _finalize(dest, op="clone", strategy="local_mirror", url=url, attempts=1)


def strategy_https_shallow(
    url: str, dest: Path, *, token: Optional[str], branch: Optional[str], depth: int,
    sparse_paths: Optional[list[str]] = None,
) -> GitEngineResult:
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    auth = _auth_url(url, token)
    argv = ["git", "clone", "--single-branch"]
    if depth and depth > 0:
        argv.append(f"--depth={int(depth)}")
    if branch:
        argv += ["--branch", branch]
    if sparse_paths:
        argv.append("--no-checkout")
    argv += ["--", auth, str(dest)]
    code, err = _run_git(argv, token=token)
    if code != 0:
        return GitEngineResult.fail(
            "clone",
            message="https_shallow_failed",
            redacted_error=err[:300],
            needs_auth=_is_auth(err, code),
            strategy_used="https_shallow",
            url=url,
        )
    # scrub token from origin
    try:
        from ..smart_clone import normalize_and_validate_url
        clean, _ = normalize_and_validate_url(url)
        if clean:
            _run_git(["git", "-C", str(dest), "remote", "set-url", "origin", clean])
    except Exception:
        pass
    if sparse_paths:
        _run_git(["git", "-C", str(dest), "sparse-checkout", "init", "--cone"])
        _run_git(["git", "-C", str(dest), "sparse-checkout", "set", *sparse_paths])
        _run_git(["git", "-C", str(dest), "checkout"])
    return _finalize(dest, op="clone", strategy="https_shallow_sparse" if sparse_paths else "https_shallow", url=url, attempts=1)


def strategy_zip_archive(url: str, dest: Path, *, token: Optional[str], branch: Optional[str]) -> GitEngineResult:
    """Last-resort: download GitHub/GitLab zipball and extract (no full git history)."""
    from ..smart_clone import normalize_and_validate_url
    clean, err = normalize_and_validate_url(url)
    if not clean:
        return GitEngineResult.fail("clone", message=err or "bad_url", strategy_used="zip_archive")
    parsed = urlparse(clean)
    host = (parsed.hostname or "").lower()
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        return GitEngineResult.fail("clone", message="cannot_derive_archive", strategy_used="zip_archive", url=url)
    owner, repo = parts[0], parts[1].removesuffix(".git")
    ref = branch or "main"
    if "github.com" in host:
        arch = f"https://api.github.com/repos/{owner}/{repo}/zipball/{ref}"
    elif "gitlab.com" in host:
        arch = f"https://gitlab.com/api/v4/projects/{owner}%2F{repo}/repository/archive.zip?sha={ref}"
    else:
        return GitEngineResult.fail("clone", message="archive_host_unsupported", strategy_used="zip_archive", url=url)

    headers = {"User-Agent": "capability-maestro-power-git"}
    if token and "github.com" in host:
        headers["Authorization"] = f"Bearer {token}"
        headers["Accept"] = "application/vnd.github+json"
    if dest.exists():
        shutil.rmtree(dest, ignore_errors=True)
    dest.mkdir(parents=True, exist_ok=True)
    tmp_zip = dest.parent / f"{dest.name}.zip"
    try:
        req = Request(arch, headers=headers)
        with urlopen(req, timeout=120) as resp, open(tmp_zip, "wb") as f:
            shutil.copyfileobj(resp, f)
        with zipfile.ZipFile(tmp_zip) as zf:
            zf.extractall(dest.parent / f"{dest.name}_extract")
        extracted = dest.parent / f"{dest.name}_extract"
        subs = [p for p in extracted.iterdir() if p.is_dir()]
        src = subs[0] if len(subs) == 1 else extracted
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.move(str(src), str(dest))
        shutil.rmtree(extracted, ignore_errors=True)
    except Exception as exc:
        needs = "401" in str(exc) or "403" in str(exc)
        return GitEngineResult.fail(
            "clone",
            message="zip_archive_failed",
            redacted_error=type(exc).__name__,
            needs_auth=needs,
            strategy_used="zip_archive",
            url=url,
        )
    finally:
        if tmp_zip.exists():
            tmp_zip.unlink(missing_ok=True)
    # init git so downstream tools still see a repo
    _run_git(["git", "-C", str(dest), "init"])
    _run_git(["git", "-C", str(dest), "remote", "add", "origin", clean])
    return _finalize(dest, op="clone", strategy="zip_archive", url=url, attempts=1)


def clone_multi_strategy(
    url: str,
    dest: Path,
    *,
    token: Optional[str] = None,
    branch: Optional[str] = None,
    depth: int = 1,
    sparse_paths: Optional[list[str]] = None,
    prefer_mirror: bool = True,
) -> GitEngineResult:
    """
    Circuit-breaker chain:
      1) local bare mirror materialize
      2) HTTPS shallow (+ optional sparse)
      3) ZIP archive fallback
    """
    attempts_log: list[dict[str, Any]] = []
    strategies = []
    if prefer_mirror:
        strategies.append(("local_mirror", lambda: strategy_local_mirror(url, dest, token=token, branch=branch, depth=depth)))
    strategies.append(
        ("https_shallow", lambda: strategy_https_shallow(
            url, dest, token=token, branch=branch, depth=depth, sparse_paths=sparse_paths
        ))
    )
    strategies.append(("zip_archive", lambda: strategy_zip_archive(url, dest, token=token, branch=branch)))

    last = GitEngineResult.fail("clone", message="no_strategy", url=url)
    for name, fn in strategies:
        logger.info("power_git strategy try=%s url=%s", name, url)
        try:
            result = fn()
        except Exception as exc:
            result = GitEngineResult.fail(
                "clone", message=f"strategy_exception:{name}", redacted_error=type(exc).__name__,
                strategy_used=name, url=url,
            )
        attempts_log.append({"strategy": name, "ok": result.ok, "error": result.redacted_error or result.message})
        result.attempts = len(attempts_log)
        result.metadata = {**(result.metadata or {}), "attempts_log": attempts_log}
        if result.ok:
            return result
        last = result
        if result.needs_auth:
            # no point trying other network strategies without token
            if not token:
                last.metadata["attempts_log"] = attempts_log
                return last
    last.metadata = {**(last.metadata or {}), "attempts_log": attempts_log}
    return last
