"""
Quality metrics — Phase 3.

Contract fidelity only. No domain template scoring.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class QualityReport:
    ok: bool = True
    score: float = 0.0
    metrics: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "score": self.score,
            "metrics": dict(self.metrics),
            "errors": list(self.errors),
            "warnings": list(self.warnings),
        }


def _handler_cmds_in_main(root: Path) -> set[str]:
    main = root / "main.py"
    if not main.exists():
        return set()
    src = main.read_text(encoding="utf-8")
    return {
        m.group(1).lower()
        for m in re.finditer(r"CommandHandler\(\s*['\"]([A-Za-z][A-Za-z0-9_]*)['\"]", src)
    }


def _model_classes(root: Path) -> set[str]:
    models = root / "app" / "models.py"
    if not models.exists():
        return set()
    src = models.read_text(encoding="utf-8")
    return set(re.findall(r"^class\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\(:]", src, re.M))


def smoke_import(root: Path) -> list[str]:
    """
    AST-level smoke: every .py file parses; main.py defines main or Application wiring.
    Does not start the bot or touch network.
    """
    errors: list[str] = []
    import ast

    for p in root.rglob("*.py"):
        try:
            ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError as e:
            errors.append(f"smoke_syntax:{p.relative_to(root)}:{e.lineno}:{e.msg}")

    main = root / "main.py"
    if not main.exists():
        errors.append("smoke_missing_main")
    else:
        src = main.read_text(encoding="utf-8")
        if "Application" not in src and "def main" not in src:
            errors.append("smoke_main_no_entry")
    return errors


def measure_quality(
    root: str | Path,
    *,
    expected_commands: list[str] | None = None,
    expected_entities: list[str] | None = None,
    structure_gate_ok: bool = True,
    code_engine_ok: bool = True,
    verify_ok: bool = True,
    compile_ok: bool = True,
) -> QualityReport:
    """
    Score project against user-grounded expectations only.
    """
    root = Path(root)
    errors: list[str] = []
    warnings: list[str] = []
    metrics: dict[str, Any] = {}

    expected_commands = [c.lstrip("/").lower() for c in (expected_commands or [])]
    expected_entities = list(expected_entities or [])

    present_cmds = _handler_cmds_in_main(root)
    metrics["commands_expected"] = expected_commands
    metrics["commands_present"] = sorted(present_cmds)

    # Coverage: expected non-structural commands present
    meaningful = [c for c in expected_commands if c not in ("start", "help")]
    if meaningful:
        covered = [c for c in meaningful if c in present_cmds]
        metrics["command_coverage"] = round(len(covered) / max(1, len(meaningful)), 3)
        missing = [c for c in meaningful if c not in present_cmds]
        if missing:
            warnings.append(f"commands_missing:{','.join(missing)}")
    else:
        metrics["command_coverage"] = 1.0 if present_cmds else 0.0

    # Invention: handlers not in expected (allow start/help)
    allowed = set(expected_commands) | {"start", "help"}
    invented = sorted(c for c in present_cmds if c not in allowed)
    metrics["invented_commands"] = invented
    if invented:
        errors.append(f"invented_commands:{','.join(invented)}")

    # Entities
    classes = _model_classes(root)
    metrics["entities_expected"] = expected_entities
    metrics["entities_present"] = sorted(classes)
    if expected_entities:
        exp_l = {e.lower(): e for e in expected_entities}
        missing_e = [e for e in expected_entities if e not in classes and e.lower() not in {c.lower() for c in classes}]
        if missing_e:
            warnings.append(f"entities_missing:{','.join(missing_e)}")
        # invented entity classes (ignore structural names)
        structural = {"Settings", "Base", "Model", "Store", "Container"}
        inv_e = [
            c for c in classes
            if c not in structural and c.lower() not in {e.lower() for e in expected_entities}
        ]
        metrics["invented_entities"] = inv_e
        if inv_e:
            errors.append(f"invented_entities:{','.join(inv_e)}")
    else:
        metrics["invented_entities"] = []

    smoke_errs = smoke_import(root)
    metrics["smoke_ok"] = len(smoke_errs) == 0
    errors.extend(smoke_errs)

    metrics["structure_gate_ok"] = structure_gate_ok
    metrics["code_engine_ok"] = code_engine_ok
    metrics["verify_ok"] = verify_ok
    metrics["compile_ok"] = compile_ok

    if not structure_gate_ok:
        errors.append("structure_gate_failed")
    if not code_engine_ok:
        errors.append("code_engine_failed")
    if not verify_ok:
        warnings.append("verify_not_ok")
    if not compile_ok:
        errors.append("compile_failed")

    # Score 0..1
    score = 0.0
    score += 0.25 * float(metrics.get("command_coverage") or 0.0)
    score += 0.15 if not invented else 0.0
    score += 0.15 if not metrics.get("invented_entities") else 0.0
    score += 0.15 if metrics.get("smoke_ok") else 0.0
    score += 0.10 if structure_gate_ok else 0.0
    score += 0.10 if code_engine_ok else 0.0
    score += 0.10 if compile_ok else 0.0
    score = round(min(1.0, score), 3)

    ok = len(errors) == 0 and score >= 0.55
    return QualityReport(ok=ok, score=score, metrics=metrics, errors=errors, warnings=warnings)
