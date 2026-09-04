"""Acceptance checks for free-path agent projects (not catalog IR lock-in)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


_ENTRY_CANDIDATES = (
    "main.py",
    "bot.py",
    "app.py",
    "src/main.py",
    "src/bot.py",
)


def check_agent_project(work_dir: str | Path, *, goal: str = "") -> dict[str, Any]:
    root = Path(work_dir)
    missing: list[str] = []
    found: list[str] = []
    warnings: list[str] = []

    if not root.exists():
        return {"ok": False, "missing": ["work_dir"], "found": [], "warnings": [], "score": 0.0}

    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    # ignore audit
    files = {f for f in files if not f.endswith("CLINE_AGENT.md")}

    entry = None
    for cand in _ENTRY_CANDIDATES:
        if cand in files:
            entry = cand
            found.append(cand)
            break
    if not entry:
        missing.append("entry_point (main.py|bot.py|app.py)")

    has_req = any(
        name in files
        for name in ("requirements.txt", "pyproject.toml", "Pipfile")
    )
    if has_req:
        found.append("deps_manifest")
    else:
        missing.append("requirements.txt|pyproject.toml")

    has_readme = any(name.lower().startswith("readme") for name in files)
    if has_readme:
        found.append("readme")
    else:
        warnings.append("no_readme")

    # Basic python content signal
    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        missing.append("any_python_file")
    else:
        found.append(f"py_count:{len(py_files)}")

    # Phase 5: entry must compile (syntax gate)
    if entry:
        try:
            import py_compile
            py_compile.compile(str(root / entry), doraise=True)
            found.append("entry_compiles")
        except Exception as exc:
            missing.append(f"entry_syntax:{type(exc).__name__}")

    # Token hygiene: no obvious hardcoded bot tokens in entry
    if entry:
        try:
            text = (root / entry).read_text(encoding="utf-8", errors="replace")
            low = text.lower()
            if "bot_token" in low or "getenv" in low or "environ" in low:
                found.append("token_from_env_likely")
            if "123456:abc" in low or "hardcoded_token" in low:
                warnings.append("possible_hardcoded_token")
            # telegram library signal
            if "telegram" in low or "aiogram" in low:
                found.append("telegram_lib_import")
            elif goal and ("بوت" in goal or "bot" in goal.lower() or "telegram" in goal.lower()):
                warnings.append("no_telegram_import_detected")
        except OSError:
            warnings.append("entry_unreadable")

    # score 0..1
    must = 3  # entry, deps, py
    got = 0
    if entry:
        got += 1
    if has_req:
        got += 1
    if py_files:
        got += 1
    score = got / must
    # Hard fail on critical missing (entry, deps, syntax, no py)
    critical = {
        m for m in missing
        if m.startswith("entry_point")
        or m.startswith("requirements")
        or m.startswith("any_python")
        or m.startswith("entry_syntax")
        or m == "work_dir"
    }
    ok = got >= 2 and bool(entry) and not critical

    return {
        "ok": ok,
        "score": round(score, 2),
        "missing": missing,
        "found": found,
        "warnings": warnings,
        "entry": entry,
        "file_count": len(files),
    }


__all__ = ["check_agent_project"]
