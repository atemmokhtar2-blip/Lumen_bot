"""
Power Git Engine — authoritative pure-git facade.

No Telegram, no AI, no business DB.
All real operations go through here (clone/push/pull/commit/branch/rollback/validate/gc).
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from .maintenance import prepare_dest_dir, unique_workdir, git_gc, gc_mirrors
from .result import GitEngineResult
from .security import (
    assert_inside_sandbox,
    ensure_strict_gitignore,
    scan_files_for_secrets,
    redact_text,
)
from .strategies import clone_multi_strategy
from .verify import structural_validate
from .workflow import (
    atomic_commit,
    create_ephemeral_branch,
    merge_ephemeral_to,
    rollback_hard,
    head_hash,
)


def _run(argv: list[str], cwd: Optional[Path] = None, timeout: int = 180, token: Optional[str] = None) -> tuple[int, str, str]:
    try:
        from lumen.engine.services.secure_exec import clean_child_environ
        env = clean_child_environ(extra={"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"})
    except Exception:
        env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", ""), "GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"}
    env["GIT_TERMINAL_PROMPT"] = "0"
    askpass = None
    try:
        from ..smart_clone import apply_git_auth_env
        askpass = apply_git_auth_env(env, token)
    except Exception:
        askpass = None
    try:
        from lumen.engine.services.secure_exec import run_git
        if not argv or argv[0] != "git":
            argv = ["git"] + list(argv or [])
        # Prefer askpass over credential-in-URL; run_git may ignore env — use subprocess if token
        if token and askpass:
            proc = subprocess.run(
                list(argv),
                cwd=str(cwd) if cwd else None,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                env=env,
            )
            out, err = proc.stdout or "", proc.stderr or ""
            code = int(proc.returncode)
        else:
            proc = run_git(list(argv), cwd=cwd, timeout=timeout)
            out, err = proc.stdout or "", proc.stderr or ""
            code = int(proc.returncode)
        if token:
            out = redact_text(out, [token])
            err = redact_text(err, [token])
        return code, out, err
    except Exception as exc:
        return 1, "", type(exc).__name__
    finally:
        if askpass:
            try:
                os.unlink(askpass)
            except OSError:
                pass
        env.pop("LUMEN_GIT_TOKEN", None)


def _inject_token(url: str, token: Optional[str]) -> str:
    if not token or not url:
        return url
    try:
        from ..smart_clone import _inject_token as _inj
        return _inj(url, token)
    except Exception:
        return url


def _is_auth(err: str, code: int) -> bool:
    try:
        from ..smart_clone import _is_auth_failure
        return _is_auth_failure(err, code)
    except Exception:
        low = (err or "").lower()
        return code in {128, 1} and any(x in low for x in ("auth", "403", "401", "denied", "could not read"))


class PowerGitEngine:
    """Authoritative engine — every mutating path must pass security + honest verify."""

    # ── Clone ────────────────────────────────────────────────────
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
        dest = prepare_dest_dir(parent, preferred_name or "repo")
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
            self._registry_put(result.path, {"url": url, "strategy": result.strategy_used})
        return result

    # ── Pull / Push ──────────────────────────────────────────────
    def pull(
        self,
        path: str | Path,
        *,
        token: Optional[str] = None,
        branch: Optional[str] = None,
    ) -> GitEngineResult:
        root = Path(path).resolve()
        if not (root / ".git").exists():
            return GitEngineResult.fail("pull", message="not_a_git_repo", path=str(root))
        code, remote, _ = _run(["git", "remote", "get-url", "origin"], cwd=root)
        remote = (remote or "").strip()
        # Auth via GIT_ASKPASS only — never rewrite origin with embedded token
        args = ["git", "pull", "--ff-only"]
        if branch:
            args = ["git", "pull", "--ff-only", "origin", branch]
        code, out, err = _run(args, cwd=root, timeout=180, token=token)
        if token and remote:
            try:
                from ..smart_clone import normalize_and_validate_url
                clean, _ = normalize_and_validate_url(remote)
                if clean:
                    _run(["git", "remote", "set-url", "origin", clean], cwd=root)
            except Exception:
                pass
        if code != 0:
            return GitEngineResult.fail(
                "pull",
                message="pull_failed",
                redacted_error=redact_text(err or out, [token or ""])[:300],
                needs_auth=_is_auth(err, code),
                path=str(root),
                url=remote or None,
                strategy_used="git_pull",
            )
        ok, details, verr = structural_validate(root)
        return GitEngineResult(
            ok=True,
            op="pull",
            strategy_used="git_pull",
            path=str(root),
            url=remote or None,
            commit_hash=head_hash(root),
            files_changed_count=int(details.get("file_count") or 0),
            validation_passed=ok,
            message="pull_ok" if ok else f"pull_ok_soft:{verr}",
            metadata=details,
        )

    def push(
        self,
        path: str | Path,
        *,
        token: Optional[str] = None,
        message: str = "update",
        remote: str = "origin",
        branch: Optional[str] = None,
        commit_first: bool = True,
    ) -> GitEngineResult:
        root = Path(path).resolve()
        if not (root / ".git").exists():
            return GitEngineResult.fail("push", message="not_a_git_repo", path=str(root))
        ensure_strict_gitignore(root)
        if commit_first:
            cr = atomic_commit(root, None, message or "update")
            if not cr.ok and cr.message == "secret_scan_blocked":
                return cr
        code, br_out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
        br = branch or (br_out.strip() if code == 0 else "main")
        if not br or br == "HEAD":
            br = "main"
        code, remote_url, _ = _run(["git", "remote", "get-url", remote], cwd=root)
        remote_url = (remote_url or "").strip()
        if code != 0 or not remote_url:
            return GitEngineResult.fail("push", message=f"no_remote:{remote}", path=str(root))
        code, out, err = _run(["git", "push", "-u", remote, br], cwd=root, timeout=180, token=token)
        if token and remote_url:
            try:
                from ..smart_clone import normalize_and_validate_url
                clean, _ = normalize_and_validate_url(remote_url)
                if clean:
                    _run(["git", "remote", "set-url", remote, clean], cwd=root)
            except Exception:
                pass
        if code != 0:
            return GitEngineResult.fail(
                "push",
                message="push_failed",
                redacted_error=redact_text(err or out, [token or ""])[:300],
                needs_auth=_is_auth(err, code),
                path=str(root),
                url=remote_url,
                strategy_used="git_push",
            )
        return GitEngineResult(
            ok=True,
            op="push",
            strategy_used="git_push",
            path=str(root),
            url=remote_url,
            commit_hash=head_hash(root),
            message=f"pushed:{remote}/{br}",
            validation_passed=True,
            metadata={"branch": br},
        )

    def create_github_repo(
        self,
        name: str,
        token: str,
        *,
        private: bool = True,
        description: str = "",
        dest_parent: str | Path | None = None,
        auto_clone: bool = True,
    ) -> GitEngineResult:
        """Create remote repo via GitHub API then optional power-clone."""
        import urllib.request
        import urllib.error
        name = (name or "").strip()
        if not re.match(r"^[A-Za-z0-9_.-]{1,100}$", name):
            return GitEngineResult.fail("create_repo", message="invalid_name")
        if not token:
            return GitEngineResult.fail("create_repo", message="token_required", needs_auth=True)
        body = json.dumps({
            "name": name,
            "private": bool(private),
            "description": (description or "")[:350],
            "auto_init": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://api.github.com/user/repos",
            data=body,
            method="POST",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "lumen-power-git",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            needs = exc.code in {401, 403}
            msg = raw[:200]
            try:
                msg = json.loads(raw).get("message") or msg
            except Exception:
                pass
            return GitEngineResult.fail(
                "create_repo",
                message=str(msg)[:200],
                needs_auth=needs,
                redacted_error=redact_text(raw, [token])[:300],
                strategy_used="github_api",
            )
        except Exception as exc:
            return GitEngineResult.fail("create_repo", message=type(exc).__name__, strategy_used="github_api")

        html_url = str(payload.get("html_url") or "")
        clone_url = str(payload.get("clone_url") or html_url)
        full_name = str(payload.get("full_name") or name)
        result = GitEngineResult(
            ok=True,
            op="create_repo",
            strategy_used="github_api",
            url=html_url or clone_url,
            message=f"created:{full_name}",
            validation_passed=True,
            metadata={
                "full_name": full_name,
                "clone_url": clone_url,
                "private": bool(payload.get("private")),
                "default_branch": payload.get("default_branch") or "main",
            },
        )
        if auto_clone and dest_parent and clone_url:
            cr = self.clone(clone_url, dest_parent, token=token, preferred_name=name)
            if cr.ok:
                result.path = cr.path
                result.strategy_used = f"github_api+{cr.strategy_used}"
                result.files_changed_count = cr.files_changed_count
                result.commit_hash = cr.commit_hash
                result.validation_passed = cr.validation_passed
                result.metadata = {**(result.metadata or {}), "clone": cr.metadata}
            else:
                result.metadata = {**(result.metadata or {}), "clone_error": cr.redacted_error or cr.message}
        return result

    # ── Commit / branch / rollback ───────────────────────────────
    def commit(self, path: str | Path, message: str, files: Iterable[Path] | None = None) -> GitEngineResult:
        return atomic_commit(Path(path), files, message)

    def start_refine(self, path: str | Path, *, job_id: str = "") -> GitEngineResult:
        return create_ephemeral_branch(Path(path), job_id=job_id)

    def finish_refine(self, path: str | Path, branch: str, *, target: str = "main", merge: bool = True) -> GitEngineResult:
        if merge:
            return merge_ephemeral_to(Path(path), branch, target=target)
        return GitEngineResult.fail("finish_refine", message="merge_disabled")

    def rollback(self, path: str | Path, ref: str = "HEAD~1") -> GitEngineResult:
        return rollback_hard(Path(path), ref)

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

    # ── UUID workdir registry (filesystem mapping, not product DB) ─
    def _registry_path(self) -> Path:
        base = Path(os.environ.get("OUTPUT_DIR") or (Path.home() / ".lumen"))
        p = base / "git_workdir_registry.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _registry_put(self, path: str, meta: dict[str, Any]) -> None:
        try:
            reg_path = self._registry_path()
            data: dict[str, Any] = {}
            if reg_path.exists():
                data = json.loads(reg_path.read_text(encoding="utf-8") or "{}")
            data[str(path)] = {**meta, "ts": int(time.time())}
            reg_path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
        except Exception:
            pass


_engine = PowerGitEngine()


def get_engine() -> PowerGitEngine:
    return _engine
