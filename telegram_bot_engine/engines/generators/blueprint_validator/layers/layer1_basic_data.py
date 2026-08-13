"""
Layer 1 — Basic Data Validation (Specification 005).

The first validation layer checks that the basic project identity
fields are present and sane.  It does **not** check deep structure or
relationships — those are covered by layers 2–6.

This layer validates:

* **Project name** — must be a non-empty, valid Python slug.
* **Bot type** — must be a non-empty string.
* **Language** — must be a non-empty string (default ``"python"``).
* **Language version** — must be a non-empty string.
* **Framework** — must be a non-empty string.
* **Database** — when declared, must be a non-empty string.  An empty
  database is acceptable when no feature requires one.
* **Display name** — should be a non-empty, human-readable string
  (warning only when missing).

Each check produces a :class:`ValidationFinding` with an appropriate
severity.  Missing required fields produce errors; missing optional
fields produce warnings.
"""

from __future__ import annotations

import re
import time
from typing import List

from ..validation_report import (
    LAYER_1_BASIC_DATA,
    LayerResult,
)
from ...project_planner.blueprint import ProjectBlueprint


# Valid Python identifier characters: letters, digits, underscores.
_SLUG_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class Layer1BasicData:
    """Layer 1: validates the basic project identity fields.

    The layer is stateless; it receives a :class:`ProjectBlueprint` and
    returns a :class:`LayerResult`.
    """

    #: The human-readable name of this layer.
    name: str = "Basic Data Validation"

    def validate(self, blueprint: ProjectBlueprint) -> LayerResult:
        """Run all basic-data checks and return the layer result."""
        start = time.perf_counter()
        result = LayerResult(
            layer_id=LAYER_1_BASIC_DATA,
            name=self.name,
        )

        identity = blueprint.identity

        # --- Project name (error when missing or invalid) ---------------
        name = identity.name or ""
        if not name:
            result.add_error(
                code="missing_project_name",
                message="The project name is missing or empty.",
                affected="identity.name",
                resolution_hint=(
                    "Set a machine-friendly project name (a valid "
                    "Python slug, e.g. 'my_store_bot')."
                ),
            )
        elif not _SLUG_PATTERN.match(name):
            result.add_error(
                code="invalid_project_name",
                message=(
                    f"The project name '{name}' is not a valid Python "
                    f"slug.  It must start with a lowercase letter and "
                    f"contain only lowercase letters, digits, and "
                    f"underscores."
                ),
                affected=name,
                resolution_hint=(
                    "Rename the project to a valid slug "
                    "(e.g. 'my_store_bot')."
                ),
            )

        # --- Display name (warning when missing) ------------------------
        if not identity.display_name:
            result.add_warning(
                code="missing_display_name",
                message="The project display name is missing.",
                affected="identity.display_name",
                resolution_hint="Set a human-readable display name.",
            )

        # --- Bot type (error when missing) ------------------------------
        bot_type = identity.bot_type or ""
        if not bot_type:
            result.add_error(
                code="missing_bot_type",
                message="The bot type is missing or empty.",
                affected="identity.bot_type",
                resolution_hint=(
                    "Set a bot type (e.g. 'store', 'group_admin', "
                    "'ai_assistant')."
                ),
            )

        # --- Language (error when missing) ------------------------------
        if not identity.language:
            result.add_error(
                code="missing_language",
                message="The programming language is missing.",
                affected="identity.language",
                resolution_hint="Set the programming language (e.g. 'python').",
            )

        # --- Language version (warning when missing) --------------------
        if not identity.language_version:
            result.add_warning(
                code="missing_language_version",
                message="The language version is missing.",
                affected="identity.language_version",
                resolution_hint="Set the language version (e.g. '3.11').",
            )

        # --- Framework (error when missing) -----------------------------
        if not identity.framework:
            result.add_error(
                code="missing_framework",
                message="The Telegram bot framework is missing.",
                affected="identity.framework",
                resolution_hint=(
                    "Set the framework (e.g. 'python-telegram-bot', "
                    "'aiogram')."
                ),
            )

        # --- Database (error when needed but missing) -------------------
        db = (identity.database or "").lower().strip()
        features_need_db = any(
            f.requires_database for f in blueprint.features
        )
        if features_need_db and not db:
            result.add_error(
                code="missing_database",
                message=(
                    "One or more features require a database but no "
                    "database backend was declared in the project "
                    "identity."
                ),
                affected=", ".join(
                    f.name for f in blueprint.features
                    if f.requires_database),
                resolution_hint=(
                    "Declare a database in the project identity "
                    "(e.g. 'sqlite', 'postgres')."
                ),
            )

        # --- Structure root (error when missing) ------------------------
        if not blueprint.structure.root:
            result.add_error(
                code="missing_structure_root",
                message="The project structure root is missing.",
                affected="structure.root",
                resolution_hint=(
                    "Set the root package name in the expected structure."
                ),
            )

        result.duration_ms = (time.perf_counter() - start) * 1000
        return result


__all__ = ["Layer1BasicData"]
