"""
Smart clone — public/private repos with optional token.

Performance:
  - shallow clone (--depth 1) by default
  - single-branch
  - no checkout of tags
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse

_URL_RE = re.compile(
    r"https?://(?:www\.)?(?:github\.com|gitlab\.com|bitbucket\.org)/[^\s]+",
    re.I,
)
_SSH_RE = re.compile(
    r"git@(?:github\.com|gitlab\.com|bitbucket\.org):[^\s]+",
    re.I,
)
_TOKEN_RE = re.compile(
    r"\b(ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|glpat-[A-Za-z0-9\-_]{20,}|gho_[A-Za-z0-9]{20,})\b"
)

_AUTH_HINTS = (
    "authentication failed",
    "could not read username",
    "invalid username or password",
    "repository not found",
    "access denied",
    "403",
    "401",
    "permission denied",
    "terminal prompts disabled",
    "could not read Password",
    "Authentication failed",
    "ERROR: Repository not found",
)


@dataclass
class CloneResult:
    ok: bool
    path: Optional[str] = None
    url: Optional[str] = None
    message: str = ""
    stderr: str = ""
    needs_auth: bool = False


def extract_repo_url(text: str) -> Optional[str]:
    text = text or ""
    m = _URL_RE.search(text)
    if m:
        url = m.group(0).rstrip(").,]>\"'")
        url = re.sub(r"/(tree|blob)/[^/]+.*$", "", url)
        url = re.sub(r"\.git$", "", url)
        if not url.endswith(".git"):
            url = url + ".git"
        return url
    m = _SSH_RE.search(text)
    if m:
        return m.group(0).rstrip(").,]>\"'")
    return None


def extract_token(text: str) -> Optional[str]:
    m = _TOKEN_RE.search(text or "")
    return m.group(1) if m else None


def looks_like_git_token(text: str) -> bool:
    return extract_token(text or "") is not None


def _inject_token(url: str, token: Optional[str]) -> str:
    if not token or not url.startswith("http"):
        return url
    p = urlparse(url)
    # GitHub recommends x-access-token for PATs
    host = p.hostname or ""
    if "github.com" in host:
        netloc = f"x-access-token:{token}@{host}"
    else:
        netloc = f"oauth2:{token}@{host}"
    if p.port:
        netloc += f":{p.port}"
    return urlunparse((p.scheme, netloc, p.path, "", "", ""))


def looks_like_clone_request(text: str) -> bool:
    t = (text or "").lower()
    triggers = (
        "اسحب", "clone", "سحب", "نزل المستودع", "نزل الريبو",
        "git clone", "pull repo", "clone repo", "جيب المستودع",
        "اسحب المستودع", "اسحب الريبو", "سحب المستودع", "clone this",
        "pull this", "download repo", "هاته من جيت", "من جithub",
    )
    has_trigger = any(x in t for x in triggers)
    has_url = extract_repo_url(text) is not None
    if has_url and not has_trigger:
        stripped = (text or "").strip()
        if len(stripped) < 120 and "github.com" in stripped.lower():
            non_url = _URL_RE.sub("", stripped).strip()
            if len(non_url) < 40:
                return True
    return has_trigger and has_url


def _diagnose_clone_error(stderr: str, returncode: int, has_token: bool) -> str:
    s = (stderr or "").lower()
    if any(x in s for x in ("could not resolve host", "name resolution", "network is unreachable")):
        return "مشكلة شبكة/DNS — تحقق من اتصال السيرفر بالإنترنت ثم أعد المحاولة"
    if any(x in s for x in ("repository not found", "not found")):
        if has_token:
            return "المستودع غير موجود أو التوكن لا يملك صلاحية عليه (تأكد من الرابط وصلاحية repo)"
        return "المستودع غير موجود أو خاص — أرسل رابط صحيح أو توكن GitHub إن كان خاصاً"
    if _is_auth_failure(stderr, returncode):
        if has_token:
            return "فشل المصادقة بتوكن GitHub — أنشئ PAT جديد بصلاحية repo"
        return "المستودع خاص — أرسل توكن GitHub (PAT) للمتابعة"
    if "timeout" in s or returncode == -9:
        return "انتهت مهلة السحب — المستودع كبير أو الشبكة بطيئة؛ أعد المحاولة"
    return f"فشل السحب (code={returncode}). التفاصيل: {(stderr or '')[:200]}"


def _is_auth_failure(stderr: str, returncode: int) -> bool:

    s = (stderr or "").lower()
    if returncode == 0:
        return False
    return any(h.lower() in s for h in _AUTH_HINTS)


def smart_clone(
    text: str,
    dest_dir: str | Path,
    token: Optional[str] = None,
    depth: Optional[int] = 1,
    url_override: Optional[str] = None,
) -> CloneResult:
    url = url_override or extract_repo_url(text)
    if not url:
        return CloneResult(ok=False, message="لم يتم العثور على رابط مستودع صالح")

    tok = token or extract_token(text)
    auth_url = _inject_token(url, tok)

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    name = Path(urlparse(url).path).stem or "repo"
    target = dest / name
    if target.exists():
        # Try to refresh existing clone (best effort)
        try:
            subprocess.run(
                ["git", "-C", str(target), "fetch", "--depth", "1", "origin"],
                capture_output=True, text=True, timeout=60, check=False,
                env={**dict(**__import__("os").environ), "GIT_TERMINAL_PROMPT": "0"},
            )
            subprocess.run(
                ["git", "-C", str(target), "reset", "--hard", "origin/HEAD"],
                capture_output=True, text=True, timeout=30, check=False,
            )
        except Exception:
            pass
        return CloneResult(
            ok=True,
            path=str(target),
            url=url,
            message=f"المجلد موجود — تم تحديثه إن أمكن: {target}",
        )

    cmd = [
        "git", "clone",
        "--single-branch",
        "--no-tags",
        "--filter=blob:none",  # partial clone for speed when supported
    ]
    if depth and depth > 0:
        cmd += ["--depth", str(depth)]
    cmd += [auth_url, str(target)]

    env = {
        **dict(**__import__("os").environ),
        "GIT_TERMINAL_PROMPT": "0",
        "GCM_INTERACTIVE": "never",
    }

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return CloneResult(ok=False, url=url, message="انتهت مهلة الـ clone")
    except Exception as e:
        return CloneResult(ok=False, url=url, message=f"فشل التشغيل: {e}")

    err = proc.stderr or proc.stdout or ""
    if tok:
        err = err.replace(tok, "***")

    # retry without partial filter if unsupported
    if proc.returncode != 0 and "filter" in err.lower() and target.exists() is False:
        cmd2 = ["git", "clone", "--single-branch", "--no-tags"]
        if depth and depth > 0:
            cmd2 += ["--depth", str(depth)]
        cmd2 += [auth_url, str(target)]
        proc = subprocess.run(cmd2, capture_output=True, text=True, timeout=180, check=False, env=env)
        err = proc.stderr or proc.stdout or ""
        if tok:
            err = err.replace(tok, "***")

    if proc.returncode != 0:
        # Auto-retry once without filter / with full history on ambiguous failures
        if target.exists() is False and "Could not resolve host" not in err:
            cmd_retry = ["git", "clone", "--single-branch", "--depth", "1", auth_url, str(target)]
            try:
                proc2 = subprocess.run(
                    cmd_retry, capture_output=True, text=True, timeout=180, check=False, env=env
                )
                err2 = proc2.stderr or proc2.stdout or ""
                if tok:
                    err2 = err2.replace(tok, "***")
                if proc2.returncode == 0:
                    return CloneResult(
                        ok=True, path=str(target), url=url,
                        message=f"تم السحب بعد إعادة محاولة ذكية: {target}",
                    )
                err = err2 or err
                proc = proc2
            except Exception:
                pass

        needs = _is_auth_failure(err, proc.returncode) and not tok
        if needs:
            return CloneResult(
                ok=False,
                url=url,
                message=(
                    "المستودع خاص أو يحتاج صلاحية.\n"
                    "أرسل توكن GitHub (PAT) بصلاحية repo في رسالة لوحده للمتابعة.\n"
                    "من: GitHub → Settings → Developer settings → Personal access tokens"
                ),
                stderr=err[:500],
                needs_auth=True,
            )
        if _is_auth_failure(err, proc.returncode) and tok:
            return CloneResult(
                ok=False,
                url=url,
                message="فشل المصادقة بالتوكن — تأكد أن الـ PAT يملك صلاحية repo",
                stderr=err[:500],
                needs_auth=True,
            )
        return CloneResult(ok=False, url=url, message=_diagnose_clone_error(err, proc.returncode, bool(tok)), stderr=err[:500])

    return CloneResult(ok=True, path=str(target), url=url, message=f"تم سحب المستودع إلى {target}")
