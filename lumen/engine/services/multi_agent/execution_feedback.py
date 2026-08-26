"""Shared execution feedback for Critic and GitHub PR agent (real subprocesses)."""
from __future__ import annotations

import os
import py_compile
import subprocess
from pathlib import Path
from typing import Any


def run_execution_feedback(root: Path) -> dict:
    """Run real process checks: compileall + import entry + optional pytest.

    This is the closed-loop signal for repair (not AST-only).
    """
    import os
    import subprocess
    import sys
    out: dict = {"ok": True, "checks": []}
    # 1) compileall
    try:
        r = subprocess.run(
            [sys.executable, "-m", "compileall", "-q", str(root)],
            capture_output=True,
            text=True,
            timeout=int(os.getenv("CRITIC_COMPILE_TIMEOUT") or "60"),
            cwd=str(root),
        )
        ok = r.returncode == 0
        out["checks"].append({"name": "compileall", "ok": ok, "stderr": (r.stderr or "")[:500]})
        if not ok:
            out["ok"] = False
    except Exception as exc:
        out["ok"] = False
        out["checks"].append({"name": "compileall", "ok": False, "error": f"{type(exc).__name__}:{exc}"})
    # 2) import main if present
    main_py = root / "main.py"
    if main_py.is_file():
        try:
            r = subprocess.run(
                [sys.executable, "-c", "import runpy; runpy.run_path('main.py', run_name='__not_main__')"],
                capture_output=True,
                text=True,
                timeout=int(os.getenv("CRITIC_IMPORT_TIMEOUT") or "20"),
                cwd=str(root),
                env={**os.environ, "LUMEN_CRITIC_IMPORT": "1"},
            )
            # run_path as __not_main__ avoids starting bot loops if guarded by __main__
            ok = r.returncode == 0
            out["checks"].append({
                "name": "import_main",
                "ok": ok,
                "stderr": (r.stderr or "")[:600],
                "stdout": (r.stdout or "")[:200],
            })
            if not ok:
                out["ok"] = False
        except Exception as exc:
            out["ok"] = False
            out["checks"].append({"name": "import_main", "ok": False, "error": f"{type(exc).__name__}:{exc}"})
    # 3) pytest if tests exist
    tests = list(root.glob("test_*.py")) + list(root.glob("tests/test_*.py"))
    if tests and (os.getenv("CRITIC_RUN_PYTEST") or "1").strip().lower() not in {"0", "false", "no"}:
        try:
            r = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", "--tb=line", "-x"],
                capture_output=True,
                text=True,
                timeout=int(os.getenv("CRITIC_PYTEST_TIMEOUT") or "90"),
                cwd=str(root),
            )
            ok = r.returncode == 0
            out["checks"].append({
                "name": "pytest",
                "ok": ok,
                "stderr": (r.stderr or "")[:400],
                "stdout": (r.stdout or "")[:400],
            })
            if not ok:
                out["ok"] = False
        except Exception as exc:
            out["checks"].append({"name": "pytest", "ok": False, "error": f"{type(exc).__name__}:{exc}"})
    return out



# backward-compatible alias
_execution_feedback_sandbox = run_execution_feedback

__all__ = ["run_execution_feedback", "_execution_feedback_sandbox"]
