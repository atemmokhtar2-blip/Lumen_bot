"""Scan generated requirements before pip install (supply-chain gate).

Layers:
  1. Strict allowlist (requirements_policy)
  2. Block known-malicious / typosquat names
  3. Prefer pinned versions; warn or refuse unpinned in production
  4. Optional pip-audit when TBE_PIP_AUDIT=1 and tool available
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

logger = logging.getLogger("tbe.dependency_scanner")

# High-confidence typosquats / malware package names seen in the wild
_TYPOSQUAT_BLOCK = {
    "python-telegram", "telegram-bot", "telegram-bot-api", "pytelegrambot",
    "request", "urllib", "beautifulsoup", "bs4-requests", "pip-install",
    "setup-tools", "colourama", "python3-dateutil", "jeIlyfish", "cryptography-fernet",
}

_PIN = re.compile(r"==\s*[\dw")
_NAME = re.compile(r"^([a-zA-Z0-9][a-zA-Z0-9._+-]*)")


def _env_prod() -> bool:
    env = (os.getenv("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()
    return env in {"production", "prod", "staging"}


def _require_pins() -> bool:
    raw = (os.getenv("TBE_REQUIRE_PINNED_DEPS") or "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return _env_prod()


def scan_requirements_text(text: str) -> tuple[bool, list[str], list[str]]:
    """Return (ok, errors, warnings). ok=False must block install."""
    errors: list[str] = []
    warnings: list[str] = []
    try:
        from lumen.engine.services.requirements_policy import (
            is_package_allowed,
            sanitize_requirements_text,
        )
        cleaned, pol_warns = sanitize_requirements_text(text or "")
        warnings.extend(pol_warns)
        text = cleaned
    except Exception as exc:
        errors.append(f"policy_sanitize_failed:{type(exc).__name__}")
        return False, errors, warnings

    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip() and not ln.strip().startswith("#")]
    if not lines:
        return True, errors, warnings

    for ln in lines:
        m = _NAME.match(ln)
        if not m:
            errors.append(f"unparseable_requirement:{ln[:60]}")
            continue
        name = m.group(1).lower().replace("_", "-")
        if name in _TYPOSQUAT_BLOCK:
            errors.append(f"typosquat_blocked:{name}")
            continue
        if not is_package_allowed(name):
            errors.append(f"not_allowlisted:{name}")
            continue
        if _require_pins() and not _PIN.search(ln) and not any(x in ln for x in (">=", "~=", "!=")):
            # unpinned in prod
            errors.append(f"unpinned_forbidden:{name}")
        elif not _PIN.search(ln):
            warnings.append(f"unpinned:{name}")

    ok = not errors
    return ok, errors, warnings


def scan_requirements_file(path: Path | str) -> tuple[bool, list[str], list[str]]:
    p = Path(path)
    if not p.is_file():
        return True, [], ["no_requirements_file"]
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return False, [f"read_failed:{type(exc).__name__}"], []
    ok, errors, warnings = scan_requirements_text(text)
    if ok and (os.getenv("TBE_PIP_AUDIT") or "").strip().lower() in {"1", "true", "yes", "on"}:
        audit_errs = _run_pip_audit(p)
        if audit_errs:
            return False, errors + audit_errs, warnings
    return ok, errors, warnings


def _run_pip_audit(req_path: Path) -> list[str]:
    """Best-effort CVE scan via pip-audit if installed."""
    try:
        r = subprocess.run(
            ["pip-audit", "-r", str(req_path), "--progress-spinner", "off"],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if r.returncode == 0:
            return []
        body = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()
        return [f"pip_audit_failed:{body[:400]}"]
    except FileNotFoundError:
        logger.info("pip-audit not installed — skipping CVE scan")
        return []
    except Exception as exc:
        return [f"pip_audit_error:{type(exc).__name__}"]
