"""Post-production verification — ensures generated bot has runnable UI."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ..services.static_dev_gate.fidelity import check_project_fidelity, fidelity_as_dict


def verify_generated_project(project_dir: str | Path) -> dict[str, Any]:
    root = Path(project_dir)
    errors: list[str] = []
    warnings: list[str] = []
    info: dict[str, Any] = {
        "has_start_handler": False,
        "button_count": 0,
        "command_handlers": 0,
        "ast_ok": True,
    }

    if not root.exists():
        return {"ok": False, "errors": ["project dir missing"], "info": info}

    # AST all python files
    for f in root.rglob("*.py"):
        try:
            ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError as e:
            info["ast_ok"] = False
            errors.append(f"syntax {f.relative_to(root)}: {e}")

    start = root / "app" / "handlers" / "start.py"
    if not start.exists():
        errors.append("missing app/handlers/start.py")
    else:
        src = start.read_text(encoding="utf-8")
        info["has_start_handler"] = "async def start_handler" in src
        info["button_count"] = src.count("InlineKeyboardButton")
        if "reply_markup" not in src:
            errors.append("start_handler does not attach reply_markup (no buttons will show)")
        if info["button_count"] < 1:
            warnings.append("no InlineKeyboardButton found in start.py")
        if "parse_mode" in src and "MARKDOWN" in src:
            warnings.append("MARKDOWN parse_mode can hide buttons if text fails to parse")

    main = root / "app" / "main.py"
    if main.exists():
        msrc = main.read_text(encoding="utf-8")
        if "CommandHandler(\"start\"" not in msrc and "CommandHandler('start'" not in msrc:
            errors.append("main.py does not register /start")
        if "CallbackQueryHandler" not in msrc:
            warnings.append("no CallbackQueryHandler — button taps may not respond")

    info["command_handlers"] = len(list((root / "app" / "handlers").glob("cmd_*.py"))) if (root / "app" / "handlers").exists() else 0

    fid = check_project_fidelity(root)
    fid_d = fidelity_as_dict(fid)
    errors.extend(fid_d.get("errors") or [])
    warnings.extend(fid_d.get("warnings") or [])
    info["fidelity"] = fid_d.get("coverage") or {}

    return {
        "ok": len(errors) == 0 and info["ast_ok"] and fid.ok,
        "errors": errors,
        "warnings": warnings,
        "info": info,
    }
