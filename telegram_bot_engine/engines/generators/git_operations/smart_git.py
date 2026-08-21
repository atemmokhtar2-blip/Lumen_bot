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
        from telegram_bot_engine.services.secure_exec import clean_child_environ
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
    """Create a new GitHub repository under the authenticated user."""
    name = (name or "").strip()
    if not re.match(r"^[A-Za-z0-9_.-]{1,100}$", name):
        return GitOpResult(ok=False, op="create_repo", message="اسم المستودع غير صالح")
    tok = (token or "").strip()
    if not tok:
        return GitOpResult(
            ok=False,
            op="create_repo",
            message="مطلوب توكن GitHub (PAT) بصلاحية repo لإنشاء مستودع",
            needs_auth=True,
        )

    body = {
        "name": name,
        "private": bool(private),
        "description": (description or "")[:350],
        "auto_init": bool(auto_init),
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        "https://api.github.com/user/repos",
        data=data,
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {tok}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
            "User-Agent": "capability-maestro-smart-git",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        needs = exc.code in {401, 403}
        msg = f"GitHub API {exc.code}"
        try:
            detail = json.loads(raw)
            msg = detail.get("message") or msg
            if isinstance(detail.get("errors"), list) and detail["errors"]:
                msg += " — " + str(detail["errors"][0])
        except Exception:
            msg = raw[:200] or msg
        return GitOpResult(
            ok=False,
            op="create_repo",
            message=msg,
            needs_auth=needs,
            stderr=_redact(raw, tok)[:400],
        )
    except Exception as exc:
        return GitOpResult(
            ok=False,
            op="create_repo",
            message=f"{type(exc).__name__}: {exc}",
            needs_auth=False,
        )

    html_url = str(payload.get("html_url") or "")
    clone_url = str(payload.get("clone_url") or html_url)
    full_name = str(payload.get("full_name") or name)
    return GitOpResult(
        ok=True,
        op="create_repo",
        url=html_url or clone_url,
        message=f"تم إنشاء المستودع {full_name}",
        data={
            "full_name": full_name,
            "clone_url": clone_url,
            "private": bool(payload.get("private")),
            "default_branch": payload.get("default_branch") or "main",
        },
    )


def git_push(
    repo_path: str | Path,
    token: Optional[str] = None,
    *,
    message: str = "update",
    remote: str = "origin",
    branch: Optional[str] = None,
) -> GitOpResult:
    """Stage, commit (if needed), and push to remote."""
    root = Path(repo_path).expanduser().resolve()
    if not (root / ".git").exists():
        return GitOpResult(ok=False, op="push", message="المسار ليس مستودع git")

    # Detect branch
    code, out, err = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=root)
    br = branch or (out.strip() if code == 0 else "main")
    if not br or br == "HEAD":
        br = "main"

    # Ensure remote URL can use token
    code, remote_url, _ = _run_git(["remote", "get-url", remote], cwd=root)
    if code != 0 or not remote_url.strip():
        return GitOpResult(
            ok=False,
            op="push",
            path=str(root),
            message=f"لا يوجد remote باسم {remote}",
        )
    remote_url = remote_url.strip()

    if token:
        auth_url = _inject_token(remote_url, token)
        if auth_url and auth_url != remote_url:
            _run_git(["remote", "set-url", remote, auth_url], cwd=root)

    # Secure atomic stage+commit (secret scan + gitignore) when dirty
    try:
        from .power.security import ensure_strict_gitignore
        from .power.workflow import atomic_commit
        ensure_strict_gitignore(root)
        code, status_out, _ = _run_git(["status", "--porcelain"], cwd=root)
        if status_out.strip():
            cr = atomic_commit(root, None, message or "update")
            if not cr.ok and cr.message == "secret_scan_blocked":
                return GitOpResult(
                    ok=False,
                    op="push",
                    path=str(root),
                    message="رفض الـ commit: أسرار مكتشفة في الملفات",
                    stderr=cr.redacted_error,
                )
    except Exception:
        _run_git(["add", "-A"], cwd=root)
        code, status_out, _ = _run_git(["status", "--porcelain"], cwd=root)
        if status_out.strip():
            _run_git(["commit", "-m", (message or "update")[:200]], cwd=root)

    code, out, err = _run_git(["push", "-u", remote, br], cwd=root, token=token, timeout=180)
    # Restore clean remote without embedded token
    if token and remote_url:
        try:
            clean, _ = normalize_and_validate_url(remote_url)
            if clean:
                _run_git(["remote", "set-url", remote, clean], cwd=root)
        except Exception:
            pass

    if code == 0:
        return GitOpResult(
            ok=True,
            op="push",
            path=str(root),
            url=remote_url,
            message=f"تم الدفع إلى {remote}/{br}",
            data={"branch": br},
        )
    needs = _is_auth_failure(err, code)
    return GitOpResult(
        ok=False,
        op="push",
        path=str(root),
        url=remote_url,
        message="فشل الدفع — يحتاج توكن بصلاحية repo" if needs else (err.strip()[:300] or "فشل الدفع"),
        needs_auth=needs,
        stderr=err[:400],
    )


def git_pull(
    repo_path: str | Path,
    token: Optional[str] = None,
    *,
    branch: Optional[str] = None,
) -> GitOpResult:
    """Pull latest changes into an existing clone."""
    root = Path(repo_path).expanduser().resolve()
    if not (root / ".git").exists():
        return GitOpResult(ok=False, op="pull", message="المسار ليس مستودع git")

    code, remote_url, _ = _run_git(["remote", "get-url", "origin"], cwd=root)
    remote_url = (remote_url or "").strip()
    if token and remote_url:
        auth_url = _inject_token(remote_url, token)
        if auth_url:
            _run_git(["remote", "set-url", "origin", auth_url], cwd=root)

    args = ["pull", "--ff-only"]
    if branch:
        args = ["pull", "--ff-only", "origin", branch]
    code, out, err = _run_git(args, cwd=root, token=token, timeout=180)

    if token and remote_url:
        try:
            clean, _ = normalize_and_validate_url(remote_url)
            if clean:
                _run_git(["remote", "set-url", "origin", clean], cwd=root)
        except Exception:
            pass

    if code == 0:
        ok, verr, meta = _verify_clone(root)
        return GitOpResult(
            ok=True,
            op="pull",
            path=str(root),
            url=remote_url or None,
            message="تم سحب آخر نسخة",
            data={"verify": verr, **(meta or {})},
        )
    needs = _is_auth_failure(err, code)
    return GitOpResult(
        ok=False,
        op="pull",
        path=str(root),
        url=remote_url or None,
        message="فشل السحب — المستودع خاص، أرسل توكن GitHub" if needs else (err.strip()[:300] or "فشل السحب"),
        needs_auth=needs,
        stderr=err[:400],
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
        result = create_github_repo(name, tok, private=private)
        # Optionally clone into dest after create
        if result.ok and dest_dir and result.data.get("clone_url"):
            clone = smart_clone(
                text=result.data["clone_url"],
                dest_dir=dest_dir,
                token=tok,
                url_override=result.data["clone_url"],
                depth=1,
            )
            if clone.ok:
                result.path = clone.path
                result.message += f"\nتم السحب محلياً: {clone.path}"
        return result

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
