"""Secure subprocess + git URL policy for untrusted inputs.

Root rules:
1. Never pass the full process environment to child processes (secret leak).
2. Git remote URLs must be HTTPS to an allow-listed host, with no embedded credentials
   and no alternative schemes (file://, git://, ssh:// with option injection).
3. Command argv is always a list (no shell=True).
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Mapping, Sequence
from urllib.parse import urlparse, unquote

# Hosts we will clone from. Override with TBE_GIT_ALLOWED_HOSTS=comma,list
_DEFAULT_HOSTS = (
    "github.com",
    "www.github.com",
    "gitlab.com",
    "www.gitlab.com",
    "bitbucket.org",
    "www.bitbucket.org",
    "codeberg.org",
    "gitea.com",
)

_BLOCKED_SCHEMES = {"file", "git", "ssh", "ftp", "ftps", "ext", "data"}
_DANGEROUS_URL_CHARS = re.compile(r"[\x00-\x1f\x7f]|--|\\n|\\r")


def allowed_git_hosts() -> set[str]:
    raw = (os.getenv("TBE_GIT_ALLOWED_HOSTS") or "").strip()
    if raw:
        return {h.strip().lower() for h in raw.split(",") if h.strip()}
    return {h.lower() for h in _DEFAULT_HOSTS}


def clean_child_environ(
    extra: Mapping[str, str] | None = None,
    *,
    keep: Sequence[str] | None = None,
) -> dict[str, str]:
    """Minimal env for child processes — strips platform secrets by default."""
    default_keep = (
        "PATH", "HOME", "USER", "LANG", "LC_ALL", "LC_CTYPE",
        "TMPDIR", "TMP", "TEMP", "SYSTEMROOT", "COMSPEC",
        "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
        "GIT_SSL_CAINFO", "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
        "http_proxy", "https_proxy", "no_proxy",
    )
    keys = tuple(keep) if keep is not None else default_keep
    env: dict[str, str] = {}
    for k in keys:
        v = os.environ.get(k)
        if v:
            env[k] = v
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    env["GIT_ASKPASS"] = "echo"
    env["PYTHONUNBUFFERED"] = "1"
    # Explicitly scrub common secret names even if someone adds them to keep
    blocked = {
        "TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TOKEN", "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY", "STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET",
        "PLATFORM_ADMIN_TOKEN", "SECRET_KEY", "TBE_TOKEN_SECRET",
        "DATABASE_URL", "MONGODB_URI", "AWS_SECRET_ACCESS_KEY",
        "GITHUB_TOKEN", "GH_TOKEN", "API_KEY",
        "GEMINI_API_KEY", "GEMINI_API_KEYS", "GOOGLE_API_KEY", "GROQ_API_KEY",
        "XAI_API_KEY", "CLINE_API_KEY", "REDIS_URL", "JOB_REDIS_URL",
        "API_KEY_PEPPER", "POSTGRES_URL", "POSTGRESQL_URL",
        "AWS_ACCESS_KEY_ID", "CAPABILITY_OPS_ADMINS",
    }
    for b in blocked:
        env.pop(b, None)
    if extra:
        for k, v in extra.items():
            if v is None:
                continue
            key = str(k)
            if key.upper() in blocked or key in blocked:
                continue
            env[key] = str(v)
    return env


def validate_git_https_url(url: str) -> str:
    """Return a normalized safe HTTPS git URL or raise ValueError."""
    raw = (url or "").strip()
    if not raw:
        raise ValueError("empty_git_url")
    if _DANGEROUS_URL_CHARS.search(raw):
        raise ValueError("dangerous_git_url_chars")
    if any(x in raw for x in (" ", "\t", "\n", "\r")):
        raise ValueError("git_url_whitespace")
    # Reject URLs that already embed credentials (user:pass@host)
    # before we parse — attackers use this to smuggle flags / confuse git
    if re.search(r"https?://[^/]*@", raw):
        raise ValueError("git_url_embedded_credentials")

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    if scheme in _BLOCKED_SCHEMES:
        raise ValueError(f"git_scheme_blocked:{scheme}")
    if scheme not in {"http", "https"}:
        # also rejects bare ssh (git@host:path)
        if raw.startswith("git@") or "://" not in raw:
            raise ValueError("git_scheme_blocked:ssh_or_opaque")
        raise ValueError(f"git_scheme_blocked:{scheme or 'none'}")

    # Force HTTPS (downgrade attack / cleartext token injection)
    if scheme != "https":
        raise ValueError("git_https_required")

    host = (parsed.hostname or "").lower()
    if not host or host not in allowed_git_hosts():
        raise ValueError(f"git_host_not_allowed:{host}")

    path = unquote(parsed.path or "")
    if not path or path == "/":
        raise ValueError("git_path_required")
    if ".." in path.split("/"):
        raise ValueError("git_path_traversal")
    # No query/fragment — git rarely needs them; blocks option smuggling
    if parsed.query or parsed.fragment:
        raise ValueError("git_url_query_fragment_forbidden")

    # Rebuild canonical URL without credentials, params, query, fragment
    safe = f"https://{host}{path}"
    if not safe.endswith(".git"):
        # keep as-is; callers may append .git
        pass
    return safe


def _git_safe_config_args() -> list[str]:
    """Disable hooks and dangerous protocols for untrusted repos."""
    return [
        "-c", "core.hooksPath=/dev/null",
        "-c", "protocol.file.allow=never",
        "-c", "protocol.ext.allow=never",
        "-c", "core.symlinks=false",
    ]


def run_git(
    args: Sequence[str],
    *,
    cwd: str | Path | None = None,
    timeout: float = 120,
    extra_env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess:
    """Run a git argv list with scrubbed environment (never shell).

    Always injects config that disables hooks and dangerous protocols so a
    malicious remote cannot run pre-checkout / post-checkout scripts on the host.
    """
    if not args or args[0] != "git":
        raise ValueError("git_argv_must_start_with_git")
    env = clean_child_environ(extra_env)
    # git [global -c ...] <subcommand> ...
    final = ["git", *_git_safe_config_args(), *list(args[1:])]
    return subprocess.run(
        final,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
        shell=False,
    )


def neutralize_git_hooks(repo_path: str | Path) -> None:
    """Remove/disable hooks after clone so nothing runs on subsequent git ops."""
    hooks = Path(repo_path) / ".git" / "hooks"
    try:
        if hooks.is_dir():
            for item in hooks.iterdir():
                try:
                    if item.is_file() or item.is_symlink():
                        item.unlink()
                    elif item.is_dir():
                        import shutil
                        shutil.rmtree(item, ignore_errors=True)
                except Exception:
                    pass
            # empty marker so git finds no executable hooks
            (hooks / "README.tbe-disabled").write_text(
                "hooks neutralized by Lumen after clone\n", encoding="utf-8"
            )
    except Exception:
        pass
