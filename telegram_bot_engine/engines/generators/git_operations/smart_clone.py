"""
Smart clone helper — understand "اسحب المستودع ده" + URL (+ optional token).

Deterministic: extracts GitHub/GitLab/Bitbucket URL and clones.
Supports HTTPS with optional personal access token.
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
_TOKEN_RE = re.compile(r"\b(ghp_[A-Za-z0-9]{20,}|glpat-[A-Za-z0-9\-_]{20,}|github_pat_[A-Za-z0-9_]{20,})\b")


@dataclass
class CloneResult:
    ok: bool
    path: Optional[str] = None
    url: Optional[str] = None
    message: str = ""
    stderr: str = ""


def extract_repo_url(text: str) -> Optional[str]:
    text = text or ""
    m = _URL_RE.search(text)
    if m:
        url = m.group(0).rstrip(").,]>\"'")
        # normalize tree/blob URLs to repo root
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


def _inject_token(url: str, token: Optional[str]) -> str:
    if not token or not url.startswith("http"):
        return url
    p = urlparse(url)
    # github: https://<token>@github.com/owner/repo.git
    netloc = f"{token}@{p.hostname}"
    if p.port:
        netloc += f":{p.port}"
    return urlunparse((p.scheme, netloc, p.path, "", "", ""))


def looks_like_clone_request(text: str) -> bool:
    t = (text or "").lower()
    triggers = (
        "اسحب", "clone", "سحب", "نزل المستودع", "نزل الريبو", "نزل الريبو",
        "git clone", "pull repo", "clone repo", "جيب المستودع",
        "اسحب المستودع", "اسحب الريبو", "سحب المستودع", "clone this",
        "pull this", "download repo", "هاته من جيت", "من جithub",
    )
    has_trigger = any(x in t for x in triggers)
    has_url = extract_repo_url(text) is not None
    # URL alone on its own line with github.com is enough if message is short
    if has_url and not has_trigger:
        stripped = (text or "").strip()
        # pure link or link + few words
        if len(stripped) < 120 and "github.com" in stripped.lower():
            # avoid treating long bot specs that happen to mention github
            non_url = _URL_RE.sub("", stripped).strip()
            if len(non_url) < 40:
                return True
    return has_trigger and has_url


def smart_clone(
    text: str,
    dest_dir: str | Path,
    token: Optional[str] = None,
    depth: Optional[int] = 1,
) -> CloneResult:
    """
    Parse natural language + URL (+ optional token) and clone the repository.
    """
    url = extract_repo_url(text)
    if not url:
        return CloneResult(ok=False, message="لم يتم العثور على رابط مستودع صالح")

    tok = token or extract_token(text)
    auth_url = _inject_token(url, tok)

    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)

    # derive folder name from repo
    name = Path(urlparse(url).path).stem or "repo"
    target = dest / name
    if target.exists():
        return CloneResult(ok=False, path=str(target), url=url, message=f"المجلد موجود مسبقاً: {target}")

    cmd = ["git", "clone"]
    if depth and depth > 0:
        cmd += ["--depth", str(depth)]
    cmd += [auth_url, str(target)]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CloneResult(ok=False, url=url, message="انتهت مهلة الـ clone")
    except Exception as e:
        return CloneResult(ok=False, url=url, message=f"فشل التشغيل: {e}")

    if proc.returncode != 0:
        # scrub token from stderr if present
        err = proc.stderr or proc.stdout or ""
        if tok:
            err = err.replace(tok, "***")
        return CloneResult(ok=False, url=url, message="فشل git clone", stderr=err[:500])

    return CloneResult(ok=True, path=str(target), url=url, message=f"تم سحب المستودع إلى {target}")
