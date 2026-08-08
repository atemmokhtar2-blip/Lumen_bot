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
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import ast


@dataclass
class LiveRunReport:
    ok: bool
    phase: str
    message: str
    bot_username: str = ""
    bot_id: int | None = None
    install_log: str = ""
    run_log: str = ""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    pid: int | None = None
    entry_point: str = ""
    venv_path: str = ""
    duration_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)

    def to_user_text(self) -> str:
        icon = "✅" if self.ok else "❌"
        lines = [f"{icon} *تشغيل حي — {self.phase}*", f"• {self.message}", "• build: `live-fix-v3`"]
        if self.bot_username:
            lines.append(f"• البوت: @{self.bot_username}")
        if self.entry_point:
            lines.append(f"• نقطة الدخول: `{self.entry_point}`")
        if self.details.get("install_mode"):
            lines.append(f"• وضع التثبيت: `{self.details['install_mode']}`")
        if self.errors:
            lines.append("• أخطاء:")
            for e in self.errors[:8]:
                lines.append(f"  - `{e[:220]}`")
        # Error Intelligence diagnosis (foundation for hosting health reports)
        if not self.ok:
            try:
                from ..error_intelligence import analyze_logs
                contract = analyze_logs(
                    run_log=self.run_log or "",
                    install_log=self.install_log or "",
                    phase=self.phase or "",
                    extra_errors=list(self.errors or []),
                )
                if contract.primary:
                    lines.append("• تشخيص:")
                    lines.append(contract.to_user_summary())
            except Exception:
                pass
        if self.warnings:
            lines.append("• تحذيرات:")
            for w in self.warnings[:4]:
                lines.append(f"  - {w[:160]}")
        # always show install tail on install failure
        if self.phase == "install" and self.install_log:
            tail = self.install_log.strip()[-800:]
            if tail:
                lines.append(f"• لوج pip:\n```\n{tail}\n```")
        elif self.run_log and not self.ok:
            tail = self.run_log.strip()[-500:]
            if tail:
                lines.append(f"• لوج:\n```\n{tail}\n```")
        if self.duration_ms:
            lines.append(f"• الزمن: {self.duration_ms:.0f}ms")
        return "\n".join(lines)


def validate_telegram_token(token: str, timeout: float = 12.0) -> tuple[bool, dict[str, Any], str]:
    token = (token or "").strip()
    if not re.match(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$", token):
        return False, {}, "شكل التوكن غير صالح"
    url = f"https://api.telegram.org/bot{token}/getMe"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")[:300]
        return False, {}, f"Telegram HTTP {e.code}: {body}"
    except Exception as e:
        return False, {}, f"فشل الاتصال بـ Telegram: {type(e).__name__}: {e}"
    if not data.get("ok"):
        return False, data, f"getMe failed: {data}"
    return True, data.get("result") or {}, "ok"


def _find_requirements(root: Path) -> Path | None:
    for name in ("requirements.txt", "requirements-bot.txt", "reqs.txt"):
        p = root / name
        if p.exists():
            return p
    return None


def _find_entry(root: Path, hints: list[str] | None = None) -> Path | None:
    for h in hints or []:
        p = root / h
        if p.exists() and p.suffix == ".py":
            return p
    for name in ("main.py", "bot.py", "app.py", "run.py"):
        p = root / name
        if p.exists():
            return p
    for p in root.glob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")[:8000]
        if any(x in text for x in ("run_polling", "start_polling", "infinity_polling", "Application.builder")):
            return p
    return None


def _venv_python(venv: Path) -> Path:
    return venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _deps_dir(root: Path) -> Path:
    d = root / ".tbe_deps"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _pip_works(py: str) -> bool:
    try:
        r = subprocess.run(
            [py, "-m", "pip", "--version"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return r.returncode == 0 and "pip" in ((r.stdout or "") + (r.stderr or "")).lower()
    except Exception:
        return False


def _bootstrap_pip(py: str) -> tuple[bool, str]:
    """Try ensurepip then get-pip.py."""
    logs = []
    r = subprocess.run(
        [py, "-m", "ensurepip", "--upgrade"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    logs.append((r.stdout or "") + (r.stderr or ""))
    if _pip_works(py):
        return True, "\n".join(logs)
    # get-pip.py
    try:
        get_pip = Path(py).resolve().parent.parent / "get-pip-tbe.py"
        # download
        url = "https://bootstrap.pypa.io/get-pip.py"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=60) as resp:
            get_pip.write_bytes(resp.read())
        r2 = subprocess.run(
            [py, str(get_pip)],
            capture_output=True,
            text=True,
            timeout=180,
        )
        logs.append((r2.stdout or "") + (r2.stderr or ""))
        try:
            get_pip.unlink(missing_ok=True)
        except Exception:
            pass
    except Exception as e:
        logs.append(f"get-pip failed: {e}")
    return _pip_works(py), "\n".join(logs)[-3000:]


def _ensure_runtime(root: Path) -> tuple[str, str, Path, str]:
    """
    Returns (python_exe, mode, isolation_path, note).
    Prefer a *working* venv with pip; else target isolation.
    """
    venv = root / ".tbe_venv"
    py_path = _venv_python(venv)
    note = ""

    # Clean broken venv (exists but no pip)
    if py_path.exists() and not _pip_works(str(py_path)):
        note = "removed_broken_venv"
        try:
            import shutil
            shutil.rmtree(venv, ignore_errors=True)
        except Exception:
            pass

    if not py_path.exists():
        r = subprocess.run(
            [sys.executable, "-m", "venv", str(venv)],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode == 0 and py_path.exists():
            if _pip_works(str(py_path)):
                return str(py_path), "venv-created", venv, note
            ok_b, blog = _bootstrap_pip(str(py_path))
            note = (note + " " + blog[-200:]).strip()
            if ok_b:
                return str(py_path), "venv-bootstrapped", venv, note
        # fall through to target
        note = (note + " venv_unusable").strip()
    else:
        if _pip_works(str(py_path)):
            return str(py_path), "venv-reused", venv, note
        ok_b, blog = _bootstrap_pip(str(py_path))
        if ok_b:
            return str(py_path), "venv-bootstrapped", venv, note
        note = (note + " " + blog[-200:]).strip()

    return sys.executable, "target", _deps_dir(root), note or "fallback_target"


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
    warnings: list[str] = []
    lines_out: list[str] = []
    for line in req.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if raw.startswith(("-e ", "--editable")) or raw.startswith("git+"):
            warnings.append(f"skipped_vcs_or_editable:{raw[:60]}")
            continue
        if raw.startswith(("-r ", "--requirement")):
            warnings.append(f"skipped_nested_req:{raw[:60]}")
            continue
        if raw.startswith("-"):
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
    when their parent framework is also listed.
    """
    lines = [ln.strip() for ln in cleaned.read_text(encoding="utf-8").splitlines() if ln.strip()]
    present = _present_packages(lines)
    to_unpin: set[str] = set()
    for framework, trans in _TRANSITIVE_WHEN.items():
        if framework in present:
            to_unpin |= {t for t in trans if t in present}

    notes: list[str] = []
    out: list[str] = []
    for raw in lines:
        parsed = _parse_req_line(raw)
        if not parsed:
            out.append(raw)
            continue
        name, rest = parsed
        if name in to_unpin and "==" in rest:
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


def _run_pip(cmd: list[str], root: Path, timeout: int = 300) -> tuple[int, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=str(root))
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

    if mode.startswith("venv"):
        _run_pip([py, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], root, timeout=180)
        base_cmd = [py, "-m", "pip", "install", "-r"]
    else:
        base_cmd = [py, "-m", "pip", "install", "--target", str(isolation), "-r"]

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
    "codecs", "locale", "gettext", "calendar", "zoneinfo",
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
    """Install specific packages one-shot (stronger than only editing requirements)."""
    if not packages:
        return True, ""
    logs: list[str] = []
    if mode.startswith("target"):
        base = [py, "-m", "pip", "install", "--target", str(isolation)]
    else:
        base = [py, "-m", "pip", "install"]
    cmd = base + packages
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


class LiveRunnerService:
    def run(
        self,
        project_path: str | Path,
        bot_token: str,
        entry_hint: str | None = None,
        run_seconds: float = float(__import__('os').environ.get('LIVE_RUN_SECONDS', 900)),
        install: bool = True,
        max_heal_rounds: int = 2,
    ) -> LiveRunReport:
        """
        Real install + run with Auto-Heal for missing dependencies.

        On ModuleNotFoundError / ImportError:
          1) map module → package
          2) append to requirements.txt if missing
          3) reinstall + rerun  (up to max_heal_rounds)
        """
        t0 = time.perf_counter()
        root = Path(project_path).resolve()
        if not root.exists():
            return LiveRunReport(ok=False, phase="validate", message="مسار المشروع غير موجود")

        ok, me, err = validate_telegram_token(bot_token)
        if not ok:
            return LiveRunReport(
                ok=False, phase="validate", message=err, errors=[err],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        username = me.get("username") or ""
        bot_id = me.get("id")

        entry = _find_entry(root, [entry_hint] if entry_hint else None)
        if entry is None:
            return LiveRunReport(
                ok=False, phase="validate",
                message="لم أجد نقطة دخول قابلة للتشغيل (main.py/bot.py/…)",
                bot_username=username, bot_id=bot_id, errors=["no_entry_point"],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        # Auto-repair common source syntax issues (e.g. \\' written literally)
        from .source_fix import repair_project_sources, discover_token_env_names, syntax_check_entry
        repair_notes = repair_project_sources(root)
        ok_syn, syn_err = syntax_check_entry(entry)
        if not ok_syn:
            return LiveRunReport(
                ok=False, phase="validate",
                message=f"SyntaxError في `{entry.name}` بعد محاولة الإصلاح: {syn_err}",
                bot_username=username, bot_id=bot_id,
                errors=[syn_err] + repair_notes[:5],
                duration_ms=(time.perf_counter() - t0) * 1000,
                details={"repair_notes": repair_notes},
            )

        # Pre-flight: AST-scan imports and ensure third-party packages are listed
        preflight_added: list[str] = []
        try:
            preflight_added = _preflight_ensure_deps(root)
        except Exception:
            preflight_added = []

        heal_notes: list[str] = list(preflight_added)
        if preflight_added:
            heal_notes = [f"preflight:{p}" for p in preflight_added]
        all_install_log = ""
        last_report: LiveRunReport | None = None

        for heal_round in range(max_heal_rounds + 1):
            report = self._attempt_install_and_run(
                root=root,
                entry=entry,
                bot_token=bot_token,
                username=username,
                bot_id=bot_id,
                run_seconds=run_seconds,
                install=install,
                repair_notes=repair_notes,
                t0=t0,
                heal_notes=heal_notes,
            )
            last_report = report
            all_install_log = (all_install_log + "\n" + (report.install_log or "")).strip()

            if report.ok:
                if heal_notes:
                    report.details = dict(report.details or {})
                    report.details["auto_healed_packages"] = list(heal_notes)
                    report.warnings = list(report.warnings or []) + [
                        f"auto_healed: {', '.join(heal_notes)}"
                    ]
                    report.message = (
                        report.message
                        + f" | تم إصلاح تبعيات ناقصة تلقائياً: {', '.join(heal_notes)}"
                    )
                report.install_log = all_install_log[-4000:]
                return report

            # ── Error Intelligence is the single decision authority ──
            if report.phase not in ("run", "install"):
                return report

            try:
                from ..error_intelligence import analyze_logs
            except Exception:
                analyze_logs = None  # type: ignore

            combined_log = (
                (report.run_log or "")
                + "\n"
                + (report.install_log or "")
                + "\n"
                + "\n".join(report.errors or [])
            )

            contract = None
            if analyze_logs is not None:
                contract = analyze_logs(
                    run_log=report.run_log or "",
                    install_log=report.install_log or "",
                    phase=report.phase or "",
                    extra_errors=list(report.errors or []),
                )
                # Enrich heal packages via AST on failing file
                source_mods = _resolve_missing_via_source(root, combined_log)
                for sm in source_mods:
                    pkg = _module_to_package(sm)
                    if pkg and pkg not in contract.heal_packages:
                        contract.heal_packages.append(pkg)
                        contract.healable = True

            # Attach diagnosis for hosting / user visibility
            report.details = dict(report.details or {})
            if contract is not None and contract.primary:
                report.details["error_contract"] = {
                    "category": contract.primary.category,
                    "action": contract.primary.suggested_action,
                    "location": contract.primary.location,
                    "package": contract.primary.suggested_package,
                    "healable": contract.healable,
                    "heal_packages": list(contract.heal_packages),
                    "summary_ar": contract.primary.summary_ar,
                    "confidence": contract.primary.confidence,
                }

            packages: list[str] = []
            if contract is not None:
                action = (
                    (contract.primary.suggested_action if contract.primary else "none")
                    or "none"
                )
                if contract.healable and contract.heal_packages and action in (
                    "install_package",
                    "fix_requirements",
                    "none",
                ):
                    packages = list(contract.heal_packages)
                elif (
                    action == "install_package"
                    and contract.primary
                    and contract.primary.suggested_package
                ):
                    packages = [contract.primary.suggested_package]
                elif action not in ("install_package", "fix_requirements", "none", ""):
                    # Error Intelligence: do not pip-heal (token/syntax/network/...)
                    report.install_log = all_install_log[-4000:]
                    loc = contract.primary.location if contract.primary else ""
                    if loc and report.message:
                        report.message = f"{report.message} | الموقع: `{loc}`"
                    report.warnings = list(report.warnings or []) + [
                        f"error_intel_action:{action}",
                        f"category:{(contract.primary.category if contract.primary else 'unknown')}",
                    ]
                    return report

            if not packages:
                missing_mods = _extract_missing_modules(combined_log)
                source_mods = _resolve_missing_via_source(root, combined_log)
                for sm in source_mods:
                    if sm not in missing_mods:
                        missing_mods.append(sm)
                for mod in missing_mods:
                    pkg = _module_to_package(mod)
                    if pkg and pkg not in packages:
                        packages.append(pkg)
                    elif not pkg:
                        heal_notes.append(f"skipped:{mod}")

            if not packages:
                report.install_log = all_install_log[-4000:]
                loc = _error_location_summary(report.run_log or "")
                if loc and report.message:
                    report.message = f"{report.message} | الموقع: `{loc}`"
                report.warnings = list(report.warnings or []) + ["not_healable_by_error_intel"]
                return report

            if heal_round >= max_heal_rounds:
                report.install_log = all_install_log[-4000:]
                report.warnings = list(report.warnings or []) + [
                    f"heal_exhausted after {max_heal_rounds} rounds; packages: {packages}"
                ]
                loc = _error_location_summary(report.run_log or "")
                if loc:
                    report.message = f"{report.message} | الموقع: `{loc}`"
                return report

            added = _ensure_packages_in_requirements(root, packages)
            if added:
                for a in added:
                    heal_notes.append(a)
            else:
                heal_notes.append(f"reinstall_try:{','.join(packages)}")

            try:
                py_h, mode_h, isolation_h, _note_h = _ensure_runtime(root)
                ok_direct, direct_log = _pip_install_packages_direct(
                    py_h, packages, root, mode_h, isolation_h
                )
                all_install_log = (
                    all_install_log + "\n--- error_intel direct pip ---\n" + direct_log
                ).strip()
                if ok_direct:
                    heal_notes.append(f"direct_pip:{','.join(packages)}")
                else:
                    heal_notes.append(f"direct_pip_failed:{','.join(packages)}")
            except Exception as e:
                heal_notes.append(f"direct_pip_error:{type(e).__name__}")

            # continue loop → reinstall + rerun

        # fallback (should not reach)
        if last_report is None:
            return LiveRunReport(ok=False, phase="run", message="heal loop failed unexpectedly")
        last_report.install_log = all_install_log[-4000:]
        return last_report

    def _attempt_install_and_run(
        self,
        *,
        root: Path,
        entry: Path,
        bot_token: str,
        username: str,
        bot_id: int | None,
        run_seconds: float,
        install: bool,
        repair_notes: list[str],
        t0: float,
        heal_notes: list[str],
    ) -> LiveRunReport:
        install_log = ""
        mode = "unknown"
        isolation = root
        py = sys.executable
        note = ""

        try:
            py, mode, isolation, note = _ensure_runtime(root)
            if install:
                req = _find_requirements(root)
                ok_i, install_log, warns = _pip_install(py, req, root, mode, isolation)
                if not ok_i:
                    # automatic fallback: if venv failed install, retry with target once
                    if mode.startswith("venv"):
                        py2, mode2, isolation2 = sys.executable, "target-fallback", _deps_dir(root)
                        ok_i2, install_log2, warns2 = _pip_install(py2, req, root, mode2, isolation2)
                        install_log = install_log + "\n--- fallback target ---\n" + install_log2
                        warns = warns + warns2
                        if ok_i2:
                            py, mode, isolation = py2, mode2, isolation2
                            ok_i = True
                        else:
                            errs = _extract_pip_errors(install_log)
                            return LiveRunReport(
                                ok=False, phase="install", message="فشل تثبيت التبعيات",
                                bot_username=username, bot_id=bot_id,
                                install_log=install_log[-6000:],
                                errors=errs,
                                warnings=warns[:5],
                                entry_point=str(entry.relative_to(root)),
                                venv_path=str(isolation),
                                duration_ms=(time.perf_counter() - t0) * 1000,
                                details={"install_mode": mode, "note": note, "heal_notes": heal_notes},
                            )
                    else:
                        errs = _extract_pip_errors(install_log)
                        return LiveRunReport(
                            ok=False, phase="install", message="فشل تثبيت التبعيات",
                            bot_username=username, bot_id=bot_id,
                            install_log=install_log[-6000:],
                            errors=errs,
                            warnings=warns[:5],
                            entry_point=str(entry.relative_to(root)),
                            venv_path=str(isolation),
                            duration_ms=(time.perf_counter() - t0) * 1000,
                            details={"install_mode": mode, "note": note, "heal_notes": heal_notes},
                        )
        except subprocess.TimeoutExpired:
            return LiveRunReport(
                ok=False, phase="install", message="انتهت مهلة تثبيت التبعيات",
                bot_username=username, bot_id=bot_id, errors=["install_timeout"],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return LiveRunReport(
                ok=False, phase="install", message=f"install error: {type(e).__name__}: {e}",
                bot_username=username, bot_id=bot_id, errors=[str(e)],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        from .source_fix import discover_token_env_names

        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        token_envs = discover_token_env_names(root)
        for key in token_envs:
            env[key] = bot_token
        for key in ("TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TOKEN", "TG_TOKEN", "API_TOKEN", "TELEGRAM_TOKEN"):
            env[key] = bot_token
        if mode.startswith("target"):
            pp = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(isolation) + (os.pathsep + pp if pp else "")

        run_log = ""
        pid = None
        try:
            proc = subprocess.Popen(
                [py, str(entry)],
                cwd=str(root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            pid = proc.pid
            try:
                out, _ = proc.communicate(timeout=run_seconds)
                run_log = out or ""
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    out, _ = proc.communicate(timeout=3)
                    run_log = out or ""
                except Exception:
                    pass
                errors = _extract_errors(run_log)
                if not errors:
                    return LiveRunReport(
                        ok=True, phase="run",
                        message=f"البوت اشتغل {run_seconds:.0f} ثانية (~{run_seconds/60:.0f} دقيقة) بدون خطأ ظاهر ثم أوقفناه حسب نافذة التشغيل.",
                        bot_username=username, bot_id=bot_id,
                        install_log=install_log[-2000:], run_log=run_log[-3000:],
                        warnings=["process_stopped_after_probe_window"],
                        pid=pid, entry_point=str(entry.relative_to(root)),
                        venv_path=str(isolation),
                        duration_ms=(time.perf_counter() - t0) * 1000,
                        details={"install_mode": mode, "probe_seconds": run_seconds, "heal_notes": heal_notes},
                    )
                return LiveRunReport(
                    ok=False, phase="run", message="أخطاء أثناء التشغيل",
                    bot_username=username, bot_id=bot_id,
                    install_log=install_log[-2000:], run_log=run_log[-4000:],
                    errors=errors, pid=pid, entry_point=str(entry.relative_to(root)),
                    venv_path=str(isolation),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    details={"install_mode": mode, "heal_notes": heal_notes},
                )

            errors = _extract_errors(run_log)
            if proc.returncode == 0 and not errors:
                return LiveRunReport(
                    ok=True, phase="run",
                    message="انتهى بكود 0 (سكربت قصير أو إقلاع ناجح).",
                    bot_username=username, bot_id=bot_id,
                    install_log=install_log[-2000:], run_log=run_log[-3000:],
                    pid=pid, entry_point=str(entry.relative_to(root)),
                    venv_path=str(isolation),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    details={"install_mode": mode, "heal_notes": heal_notes},
                )
            if not errors:
                errors = [f"process exited with code {proc.returncode}"]
            return LiveRunReport(
                ok=False, phase="run",
                message=f"توقف مبكراً (code={proc.returncode})",
                bot_username=username, bot_id=bot_id,
                install_log=install_log[-2000:], run_log=run_log[-4000:],
                errors=errors, pid=pid, entry_point=str(entry.relative_to(root)),
                venv_path=str(isolation),
                duration_ms=(time.perf_counter() - t0) * 1000,
                details={"install_mode": mode, "heal_notes": heal_notes},
            )
        except Exception as e:
            return LiveRunReport(
                ok=False, phase="run", message=f"فشل التشغيل: {type(e).__name__}: {e}",
                bot_username=username, bot_id=bot_id,
                install_log=install_log[-2000:], run_log=run_log[-2000:],
                errors=[str(e)], entry_point=str(entry.relative_to(root)),
                duration_ms=(time.perf_counter() - t0) * 1000,
                details={"heal_notes": heal_notes},
            )




def run_bot_project(
    project_path: str | Path,
    bot_token: str,
    entry_hint: str | None = None,
    run_seconds: float = float(__import__('os').environ.get('LIVE_RUN_SECONDS', 900)),
) -> LiveRunReport:
    return LiveRunnerService().run(
        project_path=project_path,
        bot_token=bot_token,
        entry_hint=entry_hint,
        run_seconds=run_seconds,
    )
