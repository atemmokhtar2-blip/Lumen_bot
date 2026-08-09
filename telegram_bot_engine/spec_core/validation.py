"""Validation Engine — validates BotSpec and generated project (no AI)."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from .registry import get_capability, known_keys
from .schema import BotSpec


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_spec(spec: BotSpec) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    if not spec.bot.name.strip():
        errors.append("bot_name_empty")
    if not spec.features:
        errors.append("no_features")
    keys = known_keys()
    seen_triggers: set[tuple[str, str]] = set()
    has_start = False
    for feat in spec.features:
        if feat.feature not in keys:
            errors.append(f"unknown_capability:{feat.feature}")
        cap = get_capability(feat.feature)
        if cap and cap.needs_target_user and feat.actor not in ("admin", "owner"):
            warnings.append(f"moderation_feature_non_admin:{feat.feature}")
        trig = (feat.trigger.type, feat.trigger.id)
        if trig in seen_triggers:
            errors.append(f"duplicate_trigger:{trig[0]}:{trig[1]}")
        seen_triggers.add(trig)
        if feat.feature == "start" or (feat.trigger.type == "command" and feat.trigger.id == "start"):
            has_start = True
        if feat.trigger.type == "command" and not feat.trigger.id:
            errors.append(f"empty_command_id:{feat.id}")
        if feat.trigger.type == "callback" and not feat.trigger.id:
            errors.append(f"empty_callback_id:{feat.id}")
    if not has_start:
        warnings.append("missing_start_feature")
    for btn in spec.start_buttons:
        if not any(
            f.trigger.type == "callback" and f.trigger.id == btn.callback_id for f in spec.features
        ):
            warnings.append(f"start_button_unbound:{btn.callback_id}")
    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


def validate_project(project_dir: str | Path) -> ValidationResult:
    root = Path(project_dir)
    errors: list[str] = []
    warnings: list[str] = []
    if not root.exists():
        return ValidationResult(False, errors=["project_missing"])
    main = root / "main.py"
    if not main.exists():
        errors.append("missing_main_py")
    req = root / "requirements.txt"
    if not req.exists():
        errors.append("missing_requirements")
    elif "python-telegram-bot" not in req.read_text(encoding="utf-8"):
        errors.append("requirements_missing_ptb")
    for py in root.rglob("*.py"):
        try:
            src = py.read_text(encoding="utf-8")
            ast.parse(src, filename=str(py))
        except SyntaxError as exc:
            errors.append(f"syntax:{py.relative_to(root)}:{exc.msg}")
        else:
            if py.name == "main.py":
                if "Application" not in src:
                    errors.append("main_missing_application")
                if "Updater(" in src or "CallbackContext" in src or "Filters." in src:
                    errors.append("main_uses_legacy_ptb_v13")
    return ValidationResult(ok=len(errors) == 0, errors=errors, warnings=warnings)


__all__ = ["ValidationResult", "validate_spec", "validate_project"]
