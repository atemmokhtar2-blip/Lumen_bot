"""Sanitize requirements.txt before any pip install (host or container).

Security model (fail-closed for generated bots):
  1. Block VCS / URL / path / archive / shell-ish lines entirely.
  2. Block known dangerous / stdlib-name packages.
  3. Strict allowlist (default ON): only curated PyPI packages used by
     Telegram bots may be installed. Unknown names are dropped.
  4. Pair with --only-binary=:all: at install time to block sdist setup.py RCE.

Disable allowlist only for trusted local tooling:
  TBE_PIP_STRICT_ALLOWLIST=0
"""
from __future__ import annotations

import os
import re
from pathlib import Path

_VCS = re.compile(r"(?i)^(git\+|hg\+|svn\+|bzr\+|http://|https://|ftp://)")
_NAME = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._+-]*$")

_BLOCKED = {
    "os", "sys", "subprocess", "ctypes", "pty", "pathlib", "socket",
    "pwn", "pwntools", "impacket", "scapy", "paramiko",
}

_ALLOWLIST = {
    "python-telegram-bot", "aiogram", "pytelegrambotapi", "telebot", "pyrogram",
    "telethon", "tgcrypto",
    "aiohttp", "httpx", "httpcore", "requests", "urllib3", "certifi", "idna",
    "charset-normalizer", "anyio", "sniffio", "h11", "h2", "hyperframe", "hpack",
    "aiosignal", "frozenlist", "multidict", "yarl", "async-timeout", "aiofiles",
    "magic-filter",
    "pydantic", "pydantic-settings", "python-dotenv", "pyyaml", "toml", "tomli",
    "orjson", "ujson", "msgpack",
    "redis", "pymongo", "motor", "sqlalchemy", "aiosqlite", "sqlite-utils",
    "psycopg", "psycopg2-binary", "asyncpg",
    "python-dateutil", "pytz", "tzdata", "babel", "pillow", "openpyxl",
    "rapidfuzz", "cachetools", "tenacity", "typing-extensions", "annotated-types",
    "attrs", "click", "rich", "tqdm",
    "cryptography", "pycryptodome", "cffi", "pycparser",
    "fastapi", "starlette", "uvicorn", "flask", "werkzeug", "jinja2", "markupsafe",
    "apscheduler", "croniter",
    "stripe",
}


def strict_allowlist_enabled() -> bool:
    raw = (os.environ.get("TBE_PIP_STRICT_ALLOWLIST") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    if raw in {"1", "true", "yes", "on"}:
        return True
    return True


def _norm(name: str) -> str:
    return (name or "").strip().lower().replace("_", "-")


def is_package_allowed(name: str) -> bool:
    n = _norm(name)
    if not n:
        return False
    blocked = {_norm(x) for x in _BLOCKED}
    if n in blocked or n.replace("-", "_") in _BLOCKED:
        return False
    if not strict_allowlist_enabled():
        return True
    return n in _ALLOWLIST


def sanitize_requirements_text(text: str) -> tuple[str, list[str]]:
    warnings: list[str] = []
    out: list[str] = []
    for raw_line in (text or "").splitlines():
        raw = raw_line.strip()
        if not raw or raw.startswith("#"):
            continue
        if " #" in raw:
            raw = raw.split(" #", 1)[0].strip()
        low = raw.lower()
        if _VCS.search(raw) or "://" in raw:
            warnings.append(f"skipped_url:{raw[:80]}")
            continue
        if raw.startswith("-") or raw.startswith("--"):
            warnings.append(f"skipped_flag:{raw[:80]}")
            continue
        if any(x in raw for x in (";", "$(", "`", "|", "&&", "||", "\n", "\r")):
            warnings.append(f"skipped_shellish:{raw[:80]}")
            continue
        name_part = re.split(r"[<>=!~;\[@]", raw)[0].strip()
        if (
            raw.startswith(("/", ".", "~"))
            or "\\" in name_part
            or "/" in name_part
        ):
            warnings.append(f"skipped_path:{raw[:80]}")
            continue
        if any(low.rstrip().endswith(ext) for ext in (".tar.gz", ".zip", ".tgz", ".whl", ".tar")):
            warnings.append(f"skipped_archive:{raw[:80]}")
            continue
        name = name_part.lower().replace("-", "_")
        if not name_part or not _NAME.match(name_part):
            warnings.append(f"skipped_invalid:{raw[:80]}")
            continue
        if name in _BLOCKED or name_part.lower() in _BLOCKED:
            warnings.append(f"skipped_blocked:{raw[:80]}")
            continue
        if not is_package_allowed(name_part):
            warnings.append(f"skipped_not_allowlisted:{raw[:80]}")
            continue
        if len(raw) > 120:
            warnings.append(f"skipped_too_long:{raw[:40]}")
            continue
        out.append(raw)
    return "\n".join(out) + ("\n" if out else ""), warnings


def sanitize_requirements_file(path: Path) -> tuple[Path, list[str]]:
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="ignore") if path.is_file() else ""
    cleaned, warnings = sanitize_requirements_text(text)
    out = path.with_name(path.stem + ".sanitized.txt")
    out.write_text(cleaned, encoding="utf-8")
    return out, warnings
