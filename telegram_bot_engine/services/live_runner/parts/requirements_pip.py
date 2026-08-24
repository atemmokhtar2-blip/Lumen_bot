"""
LiveRunner — real dependency install + bot process execution + error capture.

Install strategy (robust):
  1) try venv + ensure pip works
  2) if venv/pip broken → pip install --target .tbe_deps (isolated)
  3) surface real pip ERROR lines to the user (no opaque "pip install failed")
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import ast


from .runtime_bootstrap import _find_requirements, _deps_dir

def _parse_req_line(line: str) -> tuple[str, str] | None:
    """Return (name, rest) for a requirement line, or None if not a package pin."""
    raw = line.strip()
    if not raw or raw.startswith("#") or raw.startswith("-"):
        return None
    # name[extras]? (==|>=|<=|~=|!=|>|<) version
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)(\[[^\]]+\])?\s*(.*)$", raw)
    if not m:
        return None
    name = m.group(1).lower().replace("_", "-")
    rest = (m.group(2) or "") + (m.group(3) or "")
    return name, rest.strip()


def _parse_req_line(line: str) -> tuple[str, str] | None:
    raw = line.strip()
    if not raw or raw.startswith("#") or raw.startswith("-"):
        return None
    m = re.match(r"^([A-Za-z0-9][A-Za-z0-9_.\-]*)(\[[^\]]+\])?\s*(.*)$", raw)
    if not m:
        return None
    name = m.group(1).lower().replace("_", "-")
    rest = (m.group(2) or "") + (m.group(3) or "")
    return name, rest.strip()


# Transitive deps often hard-pinned in bot repos while frameworks need another version
_TRANSITIVE_WHEN = {
    "aiogram": {"aiofiles", "magic-filter", "aiohttp"},
    "python-telegram-bot": {"httpx", "httpcore"},
}


def _sanitize_requirements(req: Path) -> tuple[Path, list[str]]:
    """Strict sanitizer + package allowlist via requirements_policy.

    Blocks VCS/URL/path/archives and drops non-allowlisted packages (RCE/supply-chain).
    """
    from telegram_bot_engine.services.requirements_policy import sanitize_requirements_text

    warnings: list[str] = []
    raw_text = req.read_text(encoding="utf-8", errors="ignore")
    cleaned_text, pol_warns = sanitize_requirements_text(raw_text)
    warnings.extend(pol_warns)
    lines_out: list[str] = []
    for raw in cleaned_text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        name = re.split(r"[<>=!~;\[]", raw)[0].strip().lower()
        name_us = name.replace("-", "_")
        if name_us in _NEVER_PIP_INSTALL or name in _NEVER_PIP_INSTALL or name_us in _STDLIB_SKIP:
            warnings.append(f"skipped_stdlib_or_invalid:{raw[:60]}")
            continue
        lines_out.append(raw)

    cleaned = req.parent / ".tbe_requirements_clean.txt"
    cleaned.write_text("\n".join(lines_out) + ("\n" if lines_out else ""), encoding="utf-8")
    return cleaned, warnings


def _present_packages(lines: list[str]) -> set[str]:
    names = set()
    for ln in lines:
        p = _parse_req_line(ln)
        if p:
            names.add(p[0])
    return names


def _preemptive_loosen(cleaned: Path) -> tuple[Path, list[str]]:
    """
    Before first pip install: unpin transitive deps that commonly conflict
    when their parent framework is also listed. Also strip blank/comment-only
    noise and normalize Windows line endings.
    """
    raw_text = cleaned.read_text(encoding="utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    for ln in raw_text.splitlines():
        s = ln.strip()
        if not s or s.startswith("#"):
            continue
        lines.append(s)
    present = _present_packages(lines)
    to_unpin: set[str] = set()
    for framework, trans in _TRANSITIVE_WHEN.items():
        if framework in present:
            to_unpin |= {t for t in trans if t in present}
    # Always prefer framework pin; unpin known conflict companions even if
    # framework name appears only as python-telegram-bot / aiogram etc.
    if "aiogram" in present or "python-telegram-bot" in present:
        to_unpin |= {t for t in ("aiofiles", "aiohttp", "httpx", "httpcore") if t in present}

    notes: list[str] = []
    out: list[str] = []
    for raw in lines:
        parsed = _parse_req_line(raw)
        if not parsed:
            out.append(raw)
            continue
        name, rest = parsed
        if name in to_unpin and any(op in rest for op in ("==", "~=", ">=", "<=")):
            extras = ""
            em = re.match(r"(\[[^\]]+\])", rest)
            if em:
                extras = em.group(1)
            notes.append(f"preemptive_unpin:{name} ({rest})")
            out.append(name + extras)
        else:
            out.append(raw)

    path = cleaned.parent / ".tbe_requirements_ready.txt"
    path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return path, notes


def _conflict_packages_from_log(log: str) -> set[str]:
    names: set[str] = set()
    for m in re.finditer(r"user requested\s+([A-Za-z0-9_.\-]+)", log, re.I):
        names.add(m.group(1).lower().replace("_", "-"))
    for m in re.finditer(
        r"([A-Za-z0-9_.\-]+)\s+[\d.]+\s+depends on\s+([A-Za-z0-9_.\-]+)",
        log,
        re.I,
    ):
        names.add(m.group(1).lower().replace("_", "-"))
        names.add(m.group(2).lower().replace("_", "-"))
    for m in re.finditer(r"\band\s+([A-Za-z0-9_.\-]+)==", log, re.I):
        names.add(m.group(1).lower().replace("_", "-"))
    return names


def _loosen_requirements(src: Path, conflict_pkgs: set[str]) -> tuple[Path, list[str]]:
    protect = {
        "aiogram", "python-telegram-bot", "pytelegrambotapi", "telebot", "pyrogram",
    }
    notes: list[str] = []
    out: list[str] = []
    for line in src.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw:
            continue
        parsed = _parse_req_line(raw)
        if not parsed:
            out.append(raw)
            continue
        name, rest = parsed
        if name in conflict_pkgs and name not in protect and ("==" in rest or "~=" in rest or ">=" in rest):
            extras = ""
            em = re.match(r"(\[[^\]]+\])", rest)
            if em:
                extras = em.group(1)
            notes.append(f"loosened:{name} ({rest} → unpinned)")
            out.append(name + extras)
        else:
            out.append(raw)
    fixed = src.parent / ".tbe_requirements_fixed.txt"
    fixed.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return fixed, notes


def _unpin_all_hard_pins(src: Path) -> tuple[Path, list[str]]:
    protect = {
        "aiogram", "python-telegram-bot", "pytelegrambotapi", "telebot", "pyrogram",
    }
    notes: list[str] = []
    out: list[str] = []
    for line in src.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw:
            continue
        parsed = _parse_req_line(raw)
        if not parsed:
            out.append(raw)
            continue
        name, rest = parsed
        if name not in protect and "==" in rest:
            extras = ""
            em = re.match(r"(\[[^\]]+\])", rest)
            if em:
                extras = em.group(1)
            notes.append(f"unpin_all:{name}")
            out.append(name + extras)
        else:
            out.append(raw)
    path = src.parent / ".tbe_requirements_unpinned.txt"
    path.write_text("\n".join(out) + ("\n" if out else ""), encoding="utf-8")
    return path, notes


def _pip_index_flags() -> list[str]:
    """Force installs from official PyPI only (no alternate indexes / find-links)."""
    import os as _os
    index = (_os.environ.get("TBE_PIP_INDEX_URL") or "https://pypi.org/simple").strip()
    flags = ["--index-url", index, "--trusted-host", "pypi.org", "--trusted-host", "files.pythonhosted.org"]
    flags = ["--isolated", *flags]
    return flags


def _run_pip(cmd: list[str], root: Path, timeout: int = 300) -> tuple[int, str]:
    """Run pip with isolated config + official index only."""
    final = list(cmd)
    try:
        if "pip" in final and "install" in final:
            i = final.index("install")
            if "--index-url" not in final:
                final = final[: i + 1] + _pip_index_flags() + final[i + 1 :]
    except Exception:
        pass
    r = subprocess.run(final, capture_output=True, text=True, timeout=timeout, cwd=str(root))
    return r.returncode, ((r.stdout or "") + "\n" + (r.stderr or ""))


def _pip_install(py: str, req: Path | None, root: Path, mode: str, isolation: Path) -> tuple[bool, str, list[str]]:
    if not req or not req.exists():
        return True, "no requirements.txt — skipped install", []

    cleaned, warns = _sanitize_requirements(req)
    if not cleaned.read_text(encoding="utf-8").strip():
        return True, "requirements empty after sanitize — skipped", warns

    ready, prenotes = _preemptive_loosen(cleaned)
    warns.extend(prenotes)
    logs: list[str] = [f"--- install using {ready.name} (preemptive fixes: {len(prenotes)}) ---"]

    import os as _os
    wheels_only = (_os.environ.get("TBE_PIP_WHEELS_ONLY") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }
    wheel_flags = ["--only-binary=:all:"] if wheels_only else []
    if mode.startswith("venv"):
        _run_pip([py, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], root, timeout=180)
        base_cmd = [py, "-m", "pip", "install", *wheel_flags, "-r"]
    else:
        base_cmd = [py, "-m", "pip", "install", "--target", str(isolation), *wheel_flags, "-r"]

    # Pass 1: preemptive-ready file
    code, log = _run_pip(base_cmd + [str(ready)], root)
    logs.append(log)
    if code == 0:
        return True, "\n".join(logs)[-8000:], warns

    # Pass 2: conflict-based loosen
    if "ResolutionImpossible" in log or "conflicting dependencies" in log or code != 0:
        conflict_pkgs = _conflict_packages_from_log(log) or {
            (_parse_req_line(ln) or ("", ""))[0]
            for ln in ready.read_text(encoding="utf-8").splitlines()
            if _parse_req_line(ln)
        }
        fixed, notes = _loosen_requirements(ready, conflict_pkgs)
        warns.extend(notes)
        logs.append(f"--- auto-fix conflicts: {sorted(conflict_pkgs)} ---")
        code2, log2 = _run_pip(base_cmd + [str(fixed)], root)
        logs.append(log2)
        if code2 == 0:
            warns.append("auto_fixed_dependency_conflicts")
            return True, "\n".join(logs)[-8000:], warns

        # Pass 3: unpin all non-framework hard pins
        unpinned, notes3 = _unpin_all_hard_pins(ready)
        warns.extend(notes3)
        logs.append("--- auto-fix: unpin all non-framework hard pins ---")
        code3, log3 = _run_pip(base_cmd + [str(unpinned)], root)
        logs.append(log3)
        if code3 == 0:
            warns.append("auto_fixed_all_hard_pins")
            return True, "\n".join(logs)[-8000:], warns

    return False, "\n".join(logs)[-8000:], warns


def _extract_pip_errors(log: str) -> list[str]:
    if not log:
        return ["pip install failed (no log)"]
    errors: list[str] = []
    for line in log.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("ERROR") or s.startswith("error:"):
            errors.append(s[:240])
        elif "No module named pip" in s:
            errors.append(s[:240])
        elif "Could not find a version that satisfies" in s:
            errors.append(s[:240])
        elif "No matching distribution" in s:
            errors.append(s[:240])
        elif "Failed to build" in s:
            errors.append(s[:240])
        elif "subprocess-exited-with-error" in s:
            errors.append(s[:240])
    # traceback chunks
    if "Traceback (most recent call last):" in log:
        parts = re.split(r"(?=Traceback \(most recent call last\):)", log)
        for p in parts:
            if "Traceback" in p:
                errors.append(p.strip()[-300:])
    if not errors:
        # last non-empty lines as context
        tail = [ln.strip() for ln in log.splitlines() if ln.strip()][-6:]
        errors.extend(tail)
    # unique
    seen, out = set(), []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out[:10]


_ERROR_PATTERNS = (
    "Traceback (most recent call last):",
    "ModuleNotFoundError",
    "ImportError",
    "SyntaxError",
    "InvalidToken",
    "Unauthorized",
    "Conflict: terminated by other getUpdates",
)


def _extract_errors(log: str) -> list[str]:
    if not log:
        return []
    errors: list[str] = []
    parts = re.split(r"(?=Traceback \(most recent call last\):)", log)
    for p in parts:
        p = p.strip()
        if p and ("Traceback" in p or "Error" in p or "Exception" in p):
            errors.append(p[-400:])
    if not errors:
        for line in log.splitlines():
            if any(k in line for k in _ERROR_PATTERNS):
                errors.append(line.strip()[:240])
    seen, out = set(), []
    for e in errors:
        if e not in seen:
            seen.add(e)
            out.append(e)
    return out[:8]


# ---------------------------------------------------------------------------
# Auto-Heal: missing dependency → add to requirements → reinstall → rerun
# ---------------------------------------------------------------------------

# Common import-name → PyPI package mappings (deterministic, no LLM).
# Longer dotted keys are preferred over short ones (see _module_to_package).
_MODULE_TO_PACKAGE: dict[str, str] = {
    "telegram": "python-telegram-bot",
    "telegram.ext": "python-telegram-bot",
    "aiogram": "aiogram",
    "telebot": "pyTelegramBotAPI",
    "pyrogram": "pyrogram",
    "telethon": "telethon",
    "redis": "redis",
    "sqlalchemy": "SQLAlchemy",
    "PIL": "Pillow",
    "cv2": "opencv-python-headless",
    "numpy": "numpy",
    "pandas": "pandas",
    "yaml": "PyYAML",
    "dateutil": "python-dateutil",
    "motor": "motor",
    "pymongo": "pymongo",
    "asyncpg": "asyncpg",
    "aiosqlite": "aiosqlite",
    "openpyxl": "openpyxl",
    "jinja2": "Jinja2",
    "croniter": "croniter",
    "apscheduler": "APScheduler",

    "dotenv": "python-dotenv",
    "pydantic": "pydantic",
    "pydantic_settings": "pydantic-settings",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "flask": "flask",
    "django": "django",
    "requests": "requests",
    "aiohttp": "aiohttp",
    "httpx": "httpx",
    "bs4": "beautifulsoup4",
    "PIL": "Pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "yaml": "PyYAML",
    "dateutil": "python-dateutil",
    "jwt": "PyJWT",
    "Crypto": "pycryptodome",
    "Cryptodome": "pycryptodome",
    "redis": "redis",
    "celery": "celery",
    "sqlalchemy": "SQLAlchemy",
    "pymongo": "pymongo",
    "psycopg2": "psycopg2-binary",
    "MySQLdb": "mysqlclient",
    "openpyxl": "openpyxl",
    "pandas": "pandas",
    "numpy": "numpy",
    "matplotlib": "matplotlib",
    "seaborn": "seaborn",
    "rich": "rich",
    "typer": "typer",
    "click": "click",
    "tqdm": "tqdm",
    "loguru": "loguru",
    "orjson": "orjson",
    "ujson": "ujson",
    "lxml": "lxml",
    "paramiko": "paramiko",
    "boto3": "boto3",
    "stripe": "stripe",
    "openai": "openai",
    "anthropic": "anthropic",
    # Google ecosystem — NEVER install bare "google" (namespace package only)
    "google.generativeai": "google-generativeai",
    "google.genai": "google-genai",
    "google.cloud": "google-cloud-core",
    "google.auth": "google-auth",
    "google.oauth2": "google-auth",
    "googleapiclient": "google-api-python-client",
    "google.api_core": "google-api-core",
    "google.protobuf": "protobuf",
}

# stdlib modules we must never try to pip-install
_STDLIB_SKIP = {
    "os", "sys", "re", "json", "time", "datetime", "pathlib", "typing",
    "types", "builtins", "annotations", "__future__", "sysconfig",
    "collections", "functools", "itertools", "subprocess", "threading",
    "asyncio", "logging", "http", "urllib", "email", "html", "xml",
    "sqlite3", "hashlib", "hmac", "base64", "uuid", "copy", "math",
    "random", "string", "io", "tempfile", "shutil", "glob", "fnmatch",
    "argparse", "configparser", "csv", "dataclasses", "enum", "abc",
    "contextlib", "traceback", "warnings", "weakref", "gc", "inspect",
    "importlib", "pkgutil", "platform", "socket", "ssl", "select",
    "multiprocessing", "concurrent", "queue", "signal", "struct",
    "zlib", "gzip", "bz2", "lzma", "zipfile", "tarfile", "pickle",
    "shelve", "dbm", "secrets", "statistics", "decimal", "fractions",
    "numbers", "operator", "pprint", "textwrap", "unicodedata",
    "codecs", "locale", "gettext", "calendar", "zoneinfo", "tomllib",
    "graphlib", "array", "bisect", "heapq", "weakref", "atexit",
    "traceback", "linecache", "keyword", "token", "tokenize", "ast",
    "dis", "pickletools", "site", "sitecustomize", "usercustomize",
    "posixpath", "ntpath", "genericpath", "stat", "errno", "fcntl",
    "pwd", "grp", "resource", "termios", "tty", "pty", "fcntl",
    "msvcrt", "winreg", "mmap", "ctypes", "multiprocessing",
    "concurrent", "selectors", "asyncore", "asynchat", "smtplib",
    "poplib", "imaplib", "nntplib", "telnetlib", "xmlrpc", "wsgiref",
    "http", "urllib", "ipaddress", "html", "xml", "email", "mailbox",
    "mimetypes", "base64", "binhex", "binascii", "quopri", "uu",
    "json", "csv", "tomllib", "configparser", "netrc", "logging",
    "getopt", "getpass", "curses", "readline", "rlcompleter",
    "unittest", "doctest", "pydoc", "pdb", "profile", "cProfile",
    "timeit", "trace", "tracemalloc", "gc", "inspect", "site",
    "code", "codeop", "py_compile", "compileall", "dis", "pickletools",
    "formatter", "fileinput", "stat", "filecmp", "tempfile",
    "glob", "fnmatch", "linecache", "shutil", "macpath", "importlib",
    "pkgutil", "modulefinder", "runpy", "pkg_resources",
}

# Never pip-install these even if someone puts them in requirements.txt
_NEVER_PIP_INSTALL = set(_STDLIB_SKIP) | {
    "types", "typing",  # common false positives from AST / heal — not PyPI packages
}


def _extract_import_hints_from_traceback(log: str) -> list[str]:
    """
    From traceback text, pull the actual import targets shown on source lines,
    e.g.  'import google.generativeai as genai'  →  'google.generativeai'
    """
    if not log:
        return []
    hints: list[str] = []
    # lines that look like source from the failing frame
    for m in re.finditer(
        r"(?:^|\n)\s*(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))",
        log,
    ):
        mod = (m.group(1) or m.group(2) or "").strip()
        if mod and mod not in hints:
            hints.append(mod)
    return hints


def _extract_missing_modules(log: str) -> list[str]:
    """
    Extract module names from ModuleNotFoundError / ImportError.

    Prefers the full dotted name when the traceback shows the real import
    (e.g. google.generativeai) so mapping can pick the correct PyPI package.
    """
    if not log:
        return []
    found: list[str] = []
    patterns = [
        r"ModuleNotFoundError:\s*No module named ['\"]([^'\"]+)['\"]",
        r"ImportError:\s*No module named ['\"]([^'\"]+)['\"]",
        r"ImportError:\s*cannot import name ['\"][^'\"]+['\"] from ['\"]([^'\"]+)['\"]",
    ]
    raw_missing: list[str] = []
    for pat in patterns:
        for m in re.finditer(pat, log):
            mod = m.group(1).strip()
            if mod and mod not in raw_missing:
                raw_missing.append(mod)

    hints = _extract_import_hints_from_traceback(log)

    # If error says 'google' but traceback imported 'google.generativeai',
    # promote the longer hint that starts with the missing name.
    for miss in raw_missing:
        promoted = False
        for h in hints:
            if h == miss or h.startswith(miss + "."):
                if h not in found:
                    found.append(h)
                promoted = True
        if not promoted:
            if miss not in found:
                found.append(miss)

    # also keep pure hints that clearly failed
    for h in hints:
        if h not in found and any(h == m or h.startswith(m + ".") or m.startswith(h + ".") for m in raw_missing):
            found.append(h)

    return found


# Namespace / meta packages that must NEVER be pip-installed under their bare name
_BARE_NAMESPACE_BLOCKLIST = {
    "google",  # always a namespace; real packages are google-generativeai etc.
    "src",
    "lib",
    "test",
    "tests",
}


def _module_to_package(module: str) -> str | None:
    """Map import name to a PyPI package. Returns None for stdlib / unsafe bare names."""
    if not module:
        return None
    mod = module.strip()
    top = mod.split(".")[0]
    if top in _STDLIB_SKIP or mod in _STDLIB_SKIP:
        return None
    if top in _BARE_NAMESPACE_BLOCKLIST and "." not in mod:
        # bare 'google' without subpath → refuse; caller should promote via traceback hints
        return None

    # Prefer longest matching dotted key
    if mod in _MODULE_TO_PACKAGE:
        return _MODULE_TO_PACKAGE[mod]
    # try progressive prefixes: a.b.c → a.b → a
    parts = mod.split(".")
    for i in range(len(parts) - 1, 0, -1):
        prefix = ".".join(parts[:i])
        if prefix in _MODULE_TO_PACKAGE:
            return _MODULE_TO_PACKAGE[prefix]

    if top in _MODULE_TO_PACKAGE:
        return _MODULE_TO_PACKAGE[top]

    if top in _BARE_NAMESPACE_BLOCKLIST:
        return None

    # Heuristic: normal single-segment package name only
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,60}", mod):
        return mod
    return None



def _local_top_level_modules(root: Path) -> set[str]:
    """Names that resolve to local packages/modules inside the project (not third-party)."""
    local: set[str] = set()
    try:
        for p in root.rglob("*"):
            if any(x in p.parts for x in (".git", ".venv", ".tbe_venv", ".tbe_deps", "__pycache__", "site-packages")):
                continue
            if p.is_file() and p.suffix == ".py":
                if p.name == "__init__.py":
                    # package dir name
                    if p.parent != root:
                        local.add(p.parent.name)
                else:
                    local.add(p.stem)
            elif p.is_dir() and (p / "__init__.py").exists():
                local.add(p.name)
    except Exception:
        pass
    return local


def _ast_imports_in_file(path: Path) -> list[str]:
    """Return dotted module roots imported in a single Python file via AST."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="ignore"), filename=str(path))
    except Exception:
        return []
    mods: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = (alias.name or "").strip()
                if name and name not in mods:
                    mods.append(name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                name = node.module.strip()
                if name and name not in mods:
                    mods.append(name)
    return mods


def _collect_project_third_party_imports(root: Path, limit_files: int = 80) -> list[str]:
    """
    Scan project .py files with AST and return third-party import roots
    that likely need a pip package.
    """
    local = _local_top_level_modules(root)
    found: list[str] = []
    count = 0
    preferred = []
    for name in ("main.py", "bot.py", "app.py", "run.py"):
        p = root / name
        if p.exists():
            preferred.append(p)
    others = []
    try:
        for p in root.rglob("*.py"):
            if any(x in p.parts for x in (".git", ".venv", ".tbe_venv", ".tbe_deps", "__pycache__", "site-packages", "tests", "test")):
                continue
            if p in preferred:
                continue
            others.append(p)
            if len(preferred) + len(others) >= limit_files:
                break
    except Exception:
        pass

    for p in preferred + others:
        count += 1
        for mod in _ast_imports_in_file(p):
            top = mod.split(".")[0]
            if not top or top in _STDLIB_SKIP or top in local:
                continue
            # keep full dotted for better mapping (google.generativeai)
            if mod not in found:
                found.append(mod)
    return found


def _packages_from_modules(modules: list[str]) -> list[str]:
    """Map module list → unique PyPI packages (skip None)."""
    pkgs: list[str] = []
    seen: set[str] = set()
    for mod in modules:
        pkg = _module_to_package(mod)
        if not pkg:
            continue
        if pkg.lower().replace("-", "_") in _NEVER_PIP_INSTALL or pkg.lower().replace("-", "_") in _STDLIB_SKIP:
            continue
        key = pkg.lower()
        if key not in seen:
            seen.add(key)
            pkgs.append(pkg)
    return pkgs


def _failing_file_from_log(log: str, root: Path) -> Path | None:
    """Best-effort absolute path of the last traceback frame under root."""
    if not log:
        return None
    frames = re.findall(r'File "([^"]+)", line (\d+)', log)
    if not frames:
        return None
    for path_s, _ln in reversed(frames):
        p = Path(path_s)
        try:
            if p.exists() and p.suffix == ".py":
                # prefer files under root
                try:
                    p.resolve().relative_to(root.resolve())
                    return p
                except Exception:
                    if p.name and (root / p.name).exists():
                        return root / p.name
                    return p
        except Exception:
            continue
    return None


def _resolve_missing_via_source(root: Path, log: str) -> list[str]:
    """
    When traceback only says 'google', open the failing file and AST-read
    the real import targets. Filters out local project modules.
    """
    extra: list[str] = []
    fp = _failing_file_from_log(log, root)
    if fp is None:
        return extra
    local = _local_top_level_modules(root)
    for mod in _ast_imports_in_file(fp):
        top = mod.split(".")[0]
        if top in _STDLIB_SKIP or top in local:
            continue
        if mod not in extra:
            extra.append(mod)
    return extra


def _pip_install_packages_direct(
    py: str, packages: list[str], root: Path, mode: str, isolation: Path
) -> tuple[bool, str]:
    """Install specific packages one-shot — allowlist enforced, PyPI index only."""
    if not packages:
        return True, ""
    try:
        from telegram_bot_engine.services.requirements_policy import is_package_allowed
    except Exception:
        def is_package_allowed(n: str) -> bool:  # type: ignore
            return False  # fail-closed if policy missing
    safe: list[str] = []
    skipped: list[str] = []
    for pkg in packages:
        name = (pkg or "").strip()
        # strip version pins for allowlist check
        base = __import__("re").split(r"[<>=!~;\[]", name)[0].strip()
        if not base or not is_package_allowed(base):
            skipped.append(name[:60])
            continue
        safe.append(name)
    if not safe:
        return False, "all_packages_blocked_by_allowlist:" + ",".join(skipped[:8])
    logs: list[str] = []
    if skipped:
        logs.append("skipped_not_allowlisted:" + ",".join(skipped[:12]))
    import os as _os
    wheels_only = (_os.environ.get("TBE_PIP_WHEELS_ONLY") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }
    wheel_flags = ["--only-binary=:all:"] if wheels_only else []
    if mode.startswith("target"):
        base = [py, "-m", "pip", "install", "--target", str(isolation), *wheel_flags]
    else:
        base = [py, "-m", "pip", "install", *wheel_flags]
    cmd = base + safe
    code, log = _run_pip(cmd, root, timeout=300)
    logs.append(f"$ {' '.join(cmd)}\n{log}")
    return code == 0, "\n".join(logs)[-4000:]


def _preflight_ensure_deps(root: Path) -> list[str]:
    """
    Before first run: AST-scan project imports, map to packages,
    append any missing ones to requirements.txt.
    Returns list of packages added.
    """
    mods = _collect_project_third_party_imports(root)
    pkgs = _packages_from_modules(mods)
    if not pkgs:
        return []
    return _ensure_packages_in_requirements(root, pkgs)



def _packages_already_in_requirements(root: Path) -> set[str]:
    """Return normalized package names already listed in any requirements file."""
    present: set[str] = set()
    for name in ("requirements.txt", "requirements-bot.txt", "reqs.txt",
                 ".tbe_requirements_clean.txt", ".tbe_requirements_ready.txt"):
        p = root / name
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # strip extras / markers / version
                pkg = re.split(r"[<>=!~;\[]", line)[0].strip().lower()
                if pkg:
                    present.add(pkg)
                    present.add(pkg.replace("-", "_"))
                    present.add(pkg.replace("_", "-"))
        except Exception:
            continue
    return present


def _ensure_packages_in_requirements(root: Path, packages: list[str]) -> list[str]:
    """
    Append missing packages to requirements.txt.
    Creates the file if it does not exist.
    Returns the list of packages actually added.
    """
    if not packages:
        return []
    try:
        from telegram_bot_engine.services.requirements_policy import is_package_allowed
    except Exception:
        def is_package_allowed(n: str) -> bool:  # type: ignore
            return True
    packages = [
        p for p in packages
        if p
        and p.lower().replace("-", "_") not in _NEVER_PIP_INSTALL
        and p.lower().replace("-", "_") not in _STDLIB_SKIP
        and p.lower() not in {"types", "typing"}
        and is_package_allowed(p)
    ]
    if not packages:
        return []
    req = _find_requirements(root)
    if req is None:
        req = root / "requirements.txt"
        req.write_text("", encoding="utf-8")

    present = _packages_already_in_requirements(root)
    added: list[str] = []
    lines_to_append: list[str] = []

    for pkg in packages:
        norm = pkg.strip().lower()
        if not norm:
            continue
        if norm in present or norm.replace("-", "_") in present or norm.replace("_", "-") in present:
            continue
        lines_to_append.append(pkg)
        added.append(pkg)
        present.add(norm)
        present.add(norm.replace("-", "_"))
        present.add(norm.replace("_", "-"))

    if lines_to_append:
        existing = req.read_text(encoding="utf-8", errors="ignore")
        if existing and not existing.endswith("\n"):
            existing += "\n"
        # marker so humans know these were auto-added
        block = "\n".join(lines_to_append) + "\n"
        if "# auto-healed by LiveRunner" not in existing:
            existing += "\n# auto-healed by LiveRunner\n"
        existing += block
        req.write_text(existing, encoding="utf-8")

    return added


def _error_location_summary(log: str) -> str:
    """Best-effort file:line from the last traceback frame."""
    if not log:
        return ""
    # File "path", line N, in ...
    frames = re.findall(
        r'File "([^"]+)", line (\d+)',
        log,
    )
    if not frames:
        return ""
    path, line = frames[-1]
    # shorten path
    name = Path(path).name
    return f"{name}:{line}"




