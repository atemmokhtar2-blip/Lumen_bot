"""
Smart Git ops — create repo / push / pull / clone intent.

Root design:
  - Natural-language intent detection (AR + EN)
  - Token extracted from message or passed explicitly
  - needs_auth=True when private/auth fails → UX asks for PAT
  - GitHub create via REST API; push/pull via subprocess (no shell=True)
  - Reuses smart_clone normalize/verify/token helpers
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from .smart_clone import (
    CloneResult,
    extract_repo_url,
    extract_token,
    looks_like_clone_request,
    looks_like_git_token,
    normalize_and_validate_url,
    smart_clone,
    _inject_token,
    _redact,
    _is_auth_failure,
    _verify_clone,
)

logger = logging.getLogger(__name__)

# ── Intent patterns ──────────────────────────────────────────────────
_CREATE_RE = re.compile(
    r"(?:أنشئ|انشئ|انشاء|إنشاء|اعمل|سوّي|سوي|create|make)\s*"
    r"(?:مستودع|ريبو|repo|repository)|"
    r"(?:new\s+repo|create\s+repo|github\s+repo)|"
    r"مستودع\s*جديد|ريبو\s*جديد",
    re.I,
)
_PUSH_RE = re.compile(
    r"\b(?:push|بوش|ادفع|ادفعوا|ارفغ|ارفع)\b|"
    r"ادفع\s*(?:ل|على)?\s*(?:المستودع|الريبو|github)|"
    r"git\s+push",
    re.I,
)
_PULL_RE = re.compile(
    r"\b(?:pull|fetch)\b|"
    r"(?:اسحب|جيب)\s*(?:آخر|اخر)?\s*(?:نسخ[ةه]|تحديث)|"
    r"(?:حد[ّث]|حدث|حدّث)\s*(?:المستودع|الريبو|النسخ[ةه])|"
    r"git\s+pull|"
    r"آخر\s*نسخ[ةه]|اخر\s*نسخ[ةه]",
    re.I,
)
_STATUS_RE = re.compile(
    r"(?:حالة\s*(?:المستودع|الريبو|git)|git\s+status|status\s+repo)",
    re.I,
)
_REPO_NAME_RE = re.compile(
    r"(?:مستودع|ريبو|repo(?:sitory)?)\s+(?:اسمه|باسم|named?|called)?\s*[\"']?([A-Za-z0-9_.-]{2,100})[\"']?",
    re.I,
)
_REPO_NAME_RE2 = re.compile(
    r"(?:أنشئ|انشئ|create|make)\s+(?:مستودع|ريبو|repo)\s+[\"']?([A-Za-z0-9_.-]{2,100})[\"']?",
    re.I,
)
_PRIVATE_RE = re.compile(r"(?:خاص|private|سري)", re.I)


@dataclass
class GitOpResult:
    ok: bool
    op: str = ""
    path: Optional[str] = None
    url: Optional[str] = None
    message: str = ""
    needs_auth: bool = False
    stderr: str = ""
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "op": self.op,
            "path": self.path,
            "url": self.url,
            "message": self.message,
            "needs_auth": self.needs_auth,
            "stderr": (self.stderr or "")[:500],
            "data": self.data,
        }


def detect_git_intent(text: str) -> Optional[str]:
    """Return create_repo | push | pull | clone | status | None."""
    t = text or ""
    if _CREATE_RE.search(t):
        return "create_repo"
    if _PUSH_RE.search(t):
        return "push"
    if looks_like_clone_request(t) and extract_repo_url(t):
        # Explicit URL clone beats generic pull wording
        if not _PULL_RE.search(t) or extract_repo_url(t):
            if _PULL_RE.search(t) and not extract_repo_url(t):
                return "pull"
            return "clone"
    if _PULL_RE.search(t):
        return "pull"
    if looks_like_clone_request(t):
        return "clone"
    if _STATUS_RE.search(t):
        return "status"
    return None


def looks_like_git_request(text: str) -> bool:
    return detect_git_intent(text) is not None


def extract_repo_name(text: str) -> Optional[str]:
    for rx in (_REPO_NAME_RE2, _REPO_NAME_RE):
        m = rx.search(text or "")
        if m:
            name = m.group(1).strip().strip("\"'")
            if name.lower() not in {"جديد", "new", "خاص", "private", "github"}:
                return name[:100]
    # fallback: last token that looks like a repo id
    tokens = re.findall(r"\b([A-Za-z][A-Za-z0-9_.-]{1,99})\b", text or "")
    skip = {
        "github", "gitlab", "repo", "repository", "create", "make", "new",
        "private", "public", "token", "using", "with", "git", "push", "pull",
        "clone", "مستودع", "ريبو",
    }
    for tok in reversed(tokens):
        if tok.lower() not in skip and not tok.startswith("ghp_"):
            return tok
    return None


def _run_git(
    args: list[str],
    *,
    cwd: Path,
    token: Optional[str] = None,
    timeout: int = 120,
) -> tuple[int, str, str]:
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["LC_ALL"] = "C"
    # Prefer clean env if available
    try:
        from lumen.engine.services.secure_exec import clean_child_environ
        env = clean_child_environ(extra={"GIT_TERMINAL_PROMPT": "0", "LC_ALL": "C"})
    except Exception:
        pass
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            check=False,
        )
        out = proc.stdout or ""
        err = proc.stderr or ""
        if token:
            out = _redact(out, token)
            err = _redact(err, token)
        return int(proc.returncode), out, err
    except subprocess.TimeoutExpired:
        return 124, "", "git timeout"
    except Exception as exc:
        return 1, "", f"{type(exc).__name__}: {exc}"


def create_github_repo(
    name: str,
    token: str,
    *,
    private: bool = True,
    description: str = "",
    auto_init: bool = True,
) -> GitOpResult:
    """Create a new GitHub repository via PowerGitEngine."""
    from .power import get_engine
    eng = get_engine()
    r = eng.create_github_repo(name, token, private=private, description=description, auto_clone=False)
    return GitOpResult(
        ok=r.ok,
        op="create_repo",
        path=r.path,
        url=r.url,
        message=r.message,
        needs_auth=r.needs_auth,
        stderr=r.redacted_error,
        data=dict(r.metadata or {}),
    )


def git_push(
    repo_path: str | Path,
    token: Optional[str] = None,
    *,
    message: str = "update",
    remote: str = "origin",
    branch: Optional[str] = None,
) -> GitOpResult:
    """Stage/commit (secret-scanned) and push via PowerGitEngine."""
    from .power import get_engine
    r = get_engine().push(repo_path, token=token, message=message, branch=branch)
    return GitOpResult(
        ok=r.ok,
        op="push",
        path=r.path,
        url=r.url,
        message=r.message if r.ok else (r.redacted_error or r.message),
        needs_auth=r.needs_auth,
        stderr=r.redacted_error,
        data={"strategy": r.strategy_used, "commit": r.commit_hash, **(r.metadata or {})},
    )


def git_pull(
    repo_path: str | Path,
    token: Optional[str] = None,
    *,
    branch: Optional[str] = None,
) -> GitOpResult:
    """Pull latest via PowerGitEngine + structural verify."""
    from .power import get_engine
    r = get_engine().pull(repo_path, token=token, branch=branch)
    return GitOpResult(
        ok=r.ok,
        op="pull",
        path=r.path,
        url=r.url,
        message=r.message if r.ok else (r.redacted_error or r.message),
        needs_auth=r.needs_auth,
        stderr=r.redacted_error,
        data={"strategy": r.strategy_used, "commit": r.commit_hash, "validation": r.validation_passed, **(r.metadata or {})},
    )


def git_status(repo_path: str | Path) -> GitOpResult:
    root = Path(repo_path).expanduser().resolve()
    if not (root / ".git").exists():
        return GitOpResult(ok=False, op="status", message="المسار ليس مستودع git")
    code, out, err = _run_git(["status", "-sb"], cwd=root)
    code2, branch, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    code3, remote, _ = _run_git(["remote", "get-url", "origin"], cwd=root)
    return GitOpResult(
        ok=code == 0,
        op="status",
        path=str(root),
        url=(remote or "").strip() or None,
        message=(out or err or "")[:800],
        data={"branch": (branch or "").strip()},
    )


def run_git_intent(
    text: str,
    *,
    dest_dir: str | Path | None = None,
    token: Optional[str] = None,
    repo_path: str | Path | None = None,
    repo_name: Optional[str] = None,
) -> GitOpResult:
    """Dispatch NL text to the right git operation."""
    intent = detect_git_intent(text)
    tok = token or extract_token(text)

    if intent is None:
        return GitOpResult(ok=False, op="", message="لم يُفهم طلب git")

    if intent == "create_repo":
        name = repo_name or extract_repo_name(text)
        if not name:
            return GitOpResult(
                ok=False,
                op="create_repo",
                message="حدد اسم المستودع — مثال: أنشئ مستودع my-bot",
            )
        if not tok:
            return GitOpResult(
                ok=False,
                op="create_repo",
                message="لإنشاء مستودع على GitHub أرسل توكن PAT بصلاحية repo",
                needs_auth=True,
                data={"pending_name": name, "private": bool(_PRIVATE_RE.search(text or ""))},
            )
        private = bool(_PRIVATE_RE.search(text or "")) or True  # default private
        # if user said public
        if re.search(r"\bpublic\b|عام", text or "", re.I):
            private = False
        private = True
        if re.search(r"\bpublic\b|عام", text or "", re.I):
            private = False
        elif _PRIVATE_RE.search(text or ""):
            private = True
        from .power import get_engine
        eng_r = get_engine().create_github_repo(
            name, tok, private=private, dest_parent=dest_dir, auto_clone=bool(dest_dir),
        )
        return GitOpResult(
            ok=eng_r.ok,
            op="create_repo",
            path=eng_r.path,
            url=eng_r.url,
            message=eng_r.message,
            needs_auth=eng_r.needs_auth,
            stderr=eng_r.redacted_error,
            data=dict(eng_r.metadata or {}),
        )

    if intent == "clone":
        if not dest_dir:
            dest_dir = Path(os.environ.get("OUTPUT_DIR") or "/tmp/cm_clones")
        cr: CloneResult = smart_clone(text, dest_dir=dest_dir, token=tok)
        return GitOpResult(
            ok=cr.ok,
            op="clone",
            path=cr.path,
            url=cr.url,
            message=cr.message,
            needs_auth=cr.needs_auth,
            stderr=cr.stderr,
            data={"strategy": cr.strategy, "attempts": cr.attempts},
        )

    if intent == "pull":
        path = repo_path
        if not path:
            return GitOpResult(
                ok=False,
                op="pull",
                message="لا يوجد مستودع نشط — اسحب مستودع أولاً أو حدد المسار",
            )
        return git_pull(path, token=tok)

    if intent == "push":
        path = repo_path
        if not path:
            return GitOpResult(
                ok=False,
                op="push",
                message="لا يوجد مستودع نشط للدفع",
            )
        if not tok:
            # try push without token first (public/SSH agent) — still flag needs_auth on fail
            result = git_push(path, token=None)
            if not result.ok and result.needs_auth:
                return result
            if not result.ok:
                # retry signal
                result.needs_auth = result.needs_auth or True
                result.message = result.message or "أرسل توكن GitHub ثم أعد طلب البوش"
            return result
        return git_push(path, token=tok)

    if intent == "status":
        path = repo_path
        if not path:
            return GitOpResult(ok=False, op="status", message="لا يوجد مستودع نشط")
        return git_status(path)

    return GitOpResult(ok=False, op=intent or "", message="عملية غير مدعومة")


__all__ = [
    "GitOpResult",
    "detect_git_intent",
    "looks_like_git_request",
    "extract_repo_name",
    "create_github_repo",
    "git_push",
    "git_pull",
    "git_status",
    "run_git_intent",
]
