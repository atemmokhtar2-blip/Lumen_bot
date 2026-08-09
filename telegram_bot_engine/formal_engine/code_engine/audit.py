"""
Code audit — Phase 2.

Rejects generated source that invents contract surface (commands/entities)
or introduces obvious insecurity patterns. No domain template checks.
"""

from __future__ import annotations

import re
from typing import Any


_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|password|token)\s*=\s*['\"][^'\"]{8,}['\"]"),
    re.compile(r"(?i)Bearer\s+[A-Za-z0-9\-._~+/]+=*"),
)
_DANGEROUS = (
    re.compile(r"\beval\s*\("),
    re.compile(r"\bexec\s*\("),
    re.compile(r"\b__import__\s*\(\s*['\"]os['\"]"),
    re.compile(r"\bsubprocess\.(call|Popen|run)\s*\("),
    re.compile(r"\bshell\s*=\s*True"),
    re.compile(r"\bpickle\.loads\s*\("),
)


def extract_command_handlers(source: str) -> list[str]:
    names = re.findall(
        r"CommandHandler\s*\(\s*['\"]([A-Za-z][A-Za-z0-9_]*)['\"]",
        source or "",
    )
    # also cmd_foo style async defs
    names += re.findall(r"async def cmd_([A-Za-z][A-Za-z0-9_]*)\s*\(", source or "")
    out: list[str] = []
    for n in names:
        n = n.lower()
        if n not in out:
            out.append(n)
    return out


def extract_class_names(source: str) -> list[str]:
    return re.findall(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\(:]", source or "", re.M)


def audit_source(
    source: str,
    *,
    path: str,
    allowed_commands: set[str],
    allowed_entities: set[str],
) -> list[str]:
    """Return list of error codes. Empty means pass."""
    errors: list[str] = []
    src = source or ""

    for rx in _DANGEROUS:
        if rx.search(src):
            errors.append(f"dangerous_pattern:{path}:{rx.pattern[:40]}")

    for rx in _SECRET_PATTERNS:
        if rx.search(src):
            errors.append(f"hardcoded_secret:{path}")

    # Command handlers must be subset of allowed (start/help always ok)
    allowed = {c.lower() for c in allowed_commands} | {"start", "help"}
    for cmd in extract_command_handlers(src):
        if cmd not in allowed:
            errors.append(f"invented_command:{path}:{cmd}")

    # Entity classes: if allowed_entities non-empty, warn-level as error for unknown PascalCase models in models.py
    if path.replace("\\", "/").endswith("models.py") and allowed_entities:
        allowed_e = {e for e in allowed_entities}
        allowed_lower = {e.lower() for e in allowed_e}
        for cls in extract_class_names(src):
            if cls in ("Settings", "Base", "Model", "Store", "Container"):
                continue
            if cls.lower() not in allowed_lower and cls not in allowed_e:
                errors.append(f"invented_entity:{path}:{cls}")

    return errors


def audit_project_files(
    files: dict[str, str],
    *,
    allowed_commands: list[str],
    allowed_entities: list[str],
) -> list[str]:
    errors: list[str] = []
    ac = set(allowed_commands or [])
    ae = set(allowed_entities or [])
    for path, content in (files or {}).items():
        errors.extend(
            audit_source(
                content,
                path=path,
                allowed_commands=ac,
                allowed_entities=ae,
            )
        )
    return errors
