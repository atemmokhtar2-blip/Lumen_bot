"""Delivery gate — final control-plane check before user gets the ZIP."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def gate_delivery(
    project_path: str | Path,
    *,
    ir: dict[str, Any] | None = None,
    require_acceptance: bool | None = None,
) -> dict[str, Any]:
    """Return {ok, errors, warnings}. Soft by default; hard if IR_ACCEPTANCE_HARD=1."""
    root = Path(project_path)
    errors: list[str] = []
    warnings: list[str] = []

    if not root.exists():
        return {"ok": False, "errors": ["project_missing"], "warnings": warnings}
    if not (root / "main.py").exists():
        errors.append("missing_main_py")

    hard = require_acceptance
    if hard is None:
        hard = (os.getenv("IR_ACCEPTANCE_HARD") or "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    if ir and (root / "main.py").exists():
        try:
            from telegram_bot_engine.core.ir import BuildIR
            from telegram_bot_engine.core.ir_validate import check_project_against_ir

            report = check_project_against_ir(str(root), BuildIR.from_dict(ir))
            if not report.get("ok"):
                msg = "ir_acceptance_missing:" + ",".join(report.get("missing_features") or [])
                if hard:
                    errors.append(msg)
                else:
                    warnings.append(msg)
        except Exception as exc:
            warnings.append(f"acceptance_check_error:{type(exc).__name__}")

    ok = not errors
    return {"ok": ok, "errors": errors, "warnings": warnings}


__all__ = ["gate_delivery"]
