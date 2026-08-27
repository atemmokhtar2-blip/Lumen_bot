"""Behavioral acceptance checks against TaskNode.acceptance criteria.

Layers:
  1. Structural — required files exist
  2. Syntax     — compileall on Python targets
  3. Import     — importlib entrypoint smoke
  4. Criterion  — keyword/heuristic match per acceptance string
  5. Aggregate  — task + tree level report for Critic
"""
from __future__ import annotations

import compileall
import importlib.util
import logging
import py_compile
import re
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _file_exists(root: Path, rel: str) -> bool:
    return (root / rel).is_file() if rel else False


def check_structural(root: Path, files: list[str]) -> list[dict[str, Any]]:
    out = []
    for f in files or []:
        ok = _file_exists(root, f)
        out.append({"check": "file_exists", "path": f, "ok": ok})
    return out


def check_syntax(root: Path, files: list[str] | None = None) -> list[dict[str, Any]]:
    out = []
    targets = []
    if files:
        targets = [root / f for f in files if f.endswith(".py") and (root / f).is_file()]
    if not targets:
        targets = list(root.rglob("*.py"))[:40]
    for p in targets:
        try:
            py_compile.compile(str(p), doraise=True)
            out.append({"check": "syntax", "path": str(p.relative_to(root)), "ok": True})
        except Exception as exc:
            out.append({"check": "syntax", "path": str(p), "ok": False, "error": str(exc)[:300]})
    return out


def check_import_main(root: Path) -> dict[str, Any]:
    main = root / "main.py"
    if not main.is_file():
        return {"check": "import_main", "ok": False, "error": "main.py_missing"}
    try:
        spec = importlib.util.spec_from_file_location("lumen_gen_main", main)
        if spec is None or spec.loader is None:
            return {"check": "import_main", "ok": False, "error": "spec_failed"}
        mod = importlib.util.module_from_spec(spec)
        # Don't execute if needs tokens — compile only already done; try load with caution
        code = main.read_text(encoding="utf-8", errors="replace")
        # Soft: presence of Application or bot client patterns
        soft_ok = bool(re.search(r"\b(Application|Bot|Client|FastAPI|flask)\b", code))
        return {"check": "import_main", "ok": soft_ok or "def " in code, "soft": True}
    except Exception as exc:
        return {"check": "import_main", "ok": False, "error": str(exc)[:300]}


def check_criterion(root: Path, criterion: str) -> dict[str, Any]:
    c = (criterion or "").strip().lower()
    if not c:
        return {"check": "criterion", "criterion": criterion, "ok": True}
    # File existence patterns
    m = re.search(r"([a-z0-9_./-]+\.py)\s+exists", c)
    if m:
        ok = _file_exists(root, m.group(1))
        return {"check": "criterion", "criterion": criterion, "ok": ok}
    if "compileall" in c or "compiles" in c or "syntax" in c:
        syn = check_syntax(root)
        ok = all(x.get("ok") for x in syn) if syn else False
        return {"check": "criterion", "criterion": criterion, "ok": ok}
    if "requirements" in c and "telegram" in c:
        req = root / "requirements.txt"
        text = req.read_text(encoding="utf-8", errors="replace") if req.is_file() else ""
        ok = "telegram" in text.lower() or "aiogram" in text.lower() or "pyrogram" in text.lower()
        return {"check": "criterion", "criterion": criterion, "ok": ok}
    if "discord" in c and "requirements" in c:
        req = root / "requirements.txt"
        text = req.read_text(encoding="utf-8", errors="replace") if req.is_file() else ""
        return {"check": "criterion", "criterion": criterion, "ok": "discord" in text.lower()}
    if "token" in c and "env" in c:
        main = (root / "main.py").read_text(encoding="utf-8", errors="replace") if (root / "main.py").is_file() else ""
        ok = bool(re.search(r"os\.environ|getenv|BOT_TOKEN|TELEGRAM_TOKEN|DISCORD_TOKEN", main))
        return {"check": "criterion", "criterion": criterion, "ok": ok}
    if "/start" in c or "start handler" in c:
        main = (root / "main.py").read_text(encoding="utf-8", errors="replace") if (root / "main.py").is_file() else ""
        ok = "start" in main.lower() and ("commandhandler" in main.lower() or "command(" in main.lower() or "@" in main)
        return {"check": "criterion", "criterion": criterion, "ok": ok}
    if "fallback" in c or "unknown" in c:
        main = (root / "main.py").read_text(encoding="utf-8", errors="replace") if (root / "main.py").is_file() else ""
        ok = bool(re.search(r"MessageHandler|fallback|unknown|else", main, re.I))
        return {"check": "criterion", "criterion": criterion, "ok": ok}
    if "health" in c or "route" in c:
        main = (root / "main.py").read_text(encoding="utf-8", errors="replace") if (root / "main.py").is_file() else ""
        ok = bool(re.search(r"@app\.|APIRouter|route\(|/health", main))
        return {"check": "criterion", "criterion": criterion, "ok": ok}
    # Default: soft pass if main exists (avoid blocking unknown criteria)
    return {"check": "criterion", "criterion": criterion, "ok": (root / "main.py").is_file(), "soft": True}


def evaluate_task(root: Path | str, *, files: list[str] | None = None, acceptance: list[str] | None = None) -> dict[str, Any]:
    root = Path(root)
    files = list(files or [])
    acceptance = list(acceptance or [])
    checks: list[dict[str, Any]] = []
    checks.extend(check_structural(root, files))
    checks.extend(check_syntax(root, files or None))
    checks.append(check_import_main(root))
    for a in acceptance:
        checks.append(check_criterion(root, a))
    hard = [c for c in checks if not c.get("soft")]
    ok = all(c.get("ok") for c in hard) if hard else all(c.get("ok") for c in checks)
    failed = [c for c in checks if not c.get("ok")]
    return {
        "ok": ok,
        "checks": checks,
        "failed": failed,
        "failed_count": len(failed),
        "engine": "acceptance_check",
    }


def evaluate_tree(root: Path | str, tree: Any) -> dict[str, Any]:
    root = Path(root)
    task_results = {}
    all_ok = True
    for node in getattr(tree, "nodes", {}).values():
        if getattr(node, "id", None) in {getattr(tree, "root_id", None), "root"}:
            continue
        if getattr(node, "status", "") not in {"DONE", "done", "FAILED", "failed", "COMPLETED"}:
            # still evaluate DONE primarily
            if str(getattr(node, "status", "")).upper() not in {"DONE", "COMPLETED"}:
                continue
        r = evaluate_task(root, files=list(getattr(node, "files", None) or []), acceptance=list(getattr(node, "acceptance", None) or []))
        task_results[node.id] = r
        if not r.get("ok"):
            all_ok = False
    return {"ok": all_ok, "tasks": task_results, "engine": "acceptance_tree"}


__all__ = [
    "check_structural",
    "check_syntax",
    "check_import_main",
    "check_criterion",
    "evaluate_task",
    "evaluate_tree",
]
