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


