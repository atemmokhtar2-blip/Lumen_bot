"""Phase 5 — security & resource bounds (open platform, not chaos).

Hard limits for v1:
  - Python only (engine + acceptance gates)
  - No raw system commands from end users / agent in production
  - CPU / RAM / wall-time per hosted process
  - Bind 127.0.0.1 only; public traffic via reverse proxy
  - Credits: generation + hourly hosting (optionally scaled by kind)
"""
from __future__ import annotations

import os
import re
from typing import Any


# ── Language ──────────────────────────────────────────────────────────
ALLOWED_LANGUAGES = frozenset({"python", "py", ""})
FORBIDDEN_LANG_HINTS = re.compile(
    r"(?i)\b(node\.?js|typescript|golang|\bgo\b| rust\b|java\b|kotlin|php\b|ruby\b|"
    r"c\+\+|csharp|c#|swift|scala|elixir|deno|bun)\b"
)

# ── Process resources (per container / local process) ────────────────
def max_memory_mb() -> int:
    try:
        return max(64, min(int(os.getenv("TBE_BOT_MAX_MEMORY_MB") or "256"), 512))
    except Exception:
        return 256


def max_cpus() -> float:
    try:
        return max(0.1, min(float(os.getenv("TBE_BOT_MAX_CPUS") or "0.5"), 1.0))
    except Exception:
        return 0.5


def default_memory_mb() -> int:
    try:
        return max(64, min(int(os.getenv("TBE_BOT_MEMORY_MB") or "128"), max_memory_mb()))
    except Exception:
        return 128


def default_cpus() -> float:
    try:
        return max(0.1, min(float(os.getenv("TBE_BOT_CPU") or "0.25"), max_cpus()))
    except Exception:
        return 0.25


def max_host_seconds() -> int:
    """Wall-clock lifetime before soft recycle (0 = no auto-stop)."""
    try:
        return max(0, int(os.getenv("LUMEN_HOST_MAX_SECONDS") or "86400"))
    except Exception:
        return 86400


# Public traffic only via proxy — process listens on loopback
BIND_HOST = "127.0.0.1"


# ── Credits by project kind ───────────────────────────────────────────
# Multipliers on seeded UNIT costs (generation_cost=50, hourly_hosting=10)
_GEN_MULT = {
    "telegram_bot": 1.0,
    "web_site": 1.0,
    "web_api": 1.0,
    "cli_app": 0.8,
    "library": 0.8,
    "general_app": 1.0,
}
_HOST_MULT = {
    "telegram_bot": 1.0,
    "web_site": 1.2,  # slightly more for HTTP public
    "web_api": 1.2,
    "cli_app": 0.5,
    "library": 0.0,  # not typically hosted
    "general_app": 1.0,
}


def generation_credit_cost(project_kind: str = "") -> int:
    from lumen.platform.credits.onboarding import UNIT_GENERATION_COST
    k = (project_kind or "general_app").strip().lower()
    mult = float(_GEN_MULT.get(k, 1.0))
    return max(1, int(round(UNIT_GENERATION_COST * mult)))


def hourly_hosting_credit_cost(project_kind: str = "") -> int:
    from lumen.platform.credits.onboarding import UNIT_HOURLY_HOSTING
    k = (project_kind or "general_app").strip().lower()
    mult = float(_HOST_MULT.get(k, 1.0))
    if mult <= 0:
        return 0
    return max(1, int(round(UNIT_HOURLY_HOSTING * mult)))


def is_python_only_request(text: str) -> tuple[bool, str]:
    """Backward-compat gate. Prefer language_runtime.assert_language_allowed.

    Returns (ok, reason). Non-enabled languages fail.
    """
    try:
        from lumen.engine.core.language_runtime import resolve_language, assert_language_allowed
        lang, _, note = resolve_language(text or "")
        ok, reason = assert_language_allowed(lang)
        if not ok:
            return False, reason
        return True, ""
    except Exception:
        t = (text or "").strip()
        if not t:
            return True, ""
        m = FORBIDDEN_LANG_HINTS.search(t)
        if m:
            return False, f"python_only_v1:rejected_language:{m.group(0)}"
        return True, ""




_DANGEROUS_CODE = re.compile(
    r"(?m)("
    r"os\.system\s*\(|"
    r"subprocess\.[a-z_]+\([^)]*shell\s*=\s*True|"
    r"__import__\s*\(\s*['\"]os['\"]|"
    r"eval\s*\(|"
    r"exec\s*\(|"
    r"pty\.spawn|"
    r"socket\.socket\s*\([^\)]*SOCK_STREAM[^\)]*\).*connect"  # crude reverse-shell hint
    r")"
)


def scan_project_for_dangerous_code(root: str | Any) -> list[str]:
    """Static scan of .py files for raw system / shell abuse."""
    from pathlib import Path
    path = Path(root)
    if not path.is_dir():
        return []
    hits: list[str] = []
    for py in path.rglob("*.py"):
        if any(p in py.parts for p in (".venv", "venv", "__pycache__", ".git")):
            continue
        try:
            if py.stat().st_size > 400_000:
                continue
            text = py.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if _DANGEROUS_CODE.search(text):
            hits.append(str(py.relative_to(path))[:120])
            if len(hits) >= 8:
                break
    return hits


def force_loopback_bind(command: str, port: int) -> str:
    """Rewrite uvicorn/gunicorn bind from 0.0.0.0 to 127.0.0.1."""
    cmd = (command or "").strip()
    if not cmd:
        return f"uvicorn main:app --host {BIND_HOST} --port {port}"
    cmd = re.sub(r"--host\s+0\.0\.0\.0", f"--host {BIND_HOST}", cmd)
    cmd = re.sub(r"--host=0\.0\.0\.0", f"--host={BIND_HOST}", cmd)
    cmd = cmd.replace("${PORT:-8000}", str(port)).replace("$PORT", str(port))
    if "--host" not in cmd and "uvicorn" in cmd:
        cmd = cmd + f" --host {BIND_HOST} --port {port}"
    return cmd


def resource_spec_for_kind(project_kind: str = "") -> dict[str, Any]:
    mem, cpu = default_memory_mb(), default_cpus()
    try:
        from lumen.engine.services.sandbox_runtime.policy import clamp_bot_resources
        mem, cpu = clamp_bot_resources(memory_mb=mem, cpus=cpu)
    except Exception:
        mem = min(mem, max_memory_mb())
        cpu = min(cpu, max_cpus())
    return {
        "memory_mb": int(mem),
        "cpu_quota": float(cpu),
        "max_host_seconds": int(max_host_seconds()),
        "bind_host": BIND_HOST,
        "project_kind": (project_kind or "").strip().lower(),
    }


__all__ = [
    "ALLOWED_LANGUAGES",
    "BIND_HOST",
    "max_memory_mb",
    "max_cpus",
    "default_memory_mb",
    "default_cpus",
    "max_host_seconds",
    "generation_credit_cost",
    "hourly_hosting_credit_cost",
    "is_python_only_request",
    "scan_project_for_dangerous_code",
    "force_loopback_bind",
    "resource_spec_for_kind",
]
