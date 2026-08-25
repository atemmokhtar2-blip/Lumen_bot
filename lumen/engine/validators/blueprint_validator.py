"""
Blueprint validator — checks the assembled blueprint for consistency.

This validator runs during the ``validate_blueprint`` stage.  It checks
that the blueprint is internally consistent: the bot has a name, every
conversation references existing states, every command referenced by a
conversation exists, etc.
"""

from __future__ import annotations

from ..core.context import GenerationContext
from ..core.result import ValidationReport
from .base_validator import BaseValidator


class BlueprintValidator(BaseValidator):
    """Validates the structural integrity of a blueprint."""

    def __init__(self) -> None:
        super().__init__(
            name="blueprint_validator",
            description="Validates the assembled blueprint for consistency.",
            applies_to=["blueprint"],
            tags=["validation"],
        )

    def validate(self, context: GenerationContext) -> ValidationReport:
        report = self.report()
        blueprint = context.blueprint

        if blueprint is None:
            report.add_error("No blueprint attached to the context.")
            return report

        # -- meta checks ----------------------------------------------------
        if not blueprint.meta.name:
            report.add_error("Blueprint has no bot name.")
        if not blueprint.meta.name.replace("_", "").isalnum():
            report.add_error(
                f"Bot name '{blueprint.meta.name}' is not a valid identifier."
            )

        # -- command uniqueness ---------------------------------------------
        seen = set()
        for cmd in blueprint.commands:
            if cmd.name in seen:
                report.add_error(f"Duplicate command name: '{cmd.name}'.")
            seen.add(cmd.name)

        # -- conversation integrity -----------------------------------------
        for conv in blueprint.conversations:
            state_names = set(conv.state_names())
            if conv.entry_state not in state_names:
                report.add_error(
                    f"Conversation '{conv.name}': entry state "
                    f"'{conv.entry_state}' not in states {state_names}."
                )
            for state in conv.states:
                if state.next_state and state.next_state not in state_names:
                    if state.next_state != conv.exit_state:
                        report.add_error(
                            f"Conversation '{conv.name}': state '{state.name}' "
                            f"references unknown next state '{state.next_state}'."
                        )

        if report.passed:
            self._log.info("Blueprint validation passed",
                           {"commands": len(blueprint.commands),
                            "conversations": len(blueprint.conversations)})
        else:
            self._log.warning("Blueprint validation failed",
                              {"errors": len(report.errors)})

        return report


__all__ = ["BlueprintValidator"]
