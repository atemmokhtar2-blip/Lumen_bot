"""
Base validator — shared boilerplate for validator implementations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..core.contracts import Validator
from ..core.result import ValidationReport
from ..logging import get_logger


class BaseValidator(Validator):
    """Convenience base class for validators."""

    def __init__(self, name: str, version: str = "1.0.0",
                 description: str = "",
                 applies_to: Optional[List[str]] = None,
                 tags: Optional[List[str]] = None,
                 metadata: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            name=name, version=version, description=description,
            tags=tags or [],
            metadata=metadata or {},
        )
        if applies_to:
            self.metadata["applies_to"] = applies_to
        self._log = get_logger(f"validator.{name}")

    def report(self) -> ValidationReport:
        return ValidationReport(validator_name=self.name)

    def validate(self, context):  # type: ignore[override]
        raise NotImplementedError(
            f"Validator '{self.name}' must implement validate()."
        )


__all__ = ["BaseValidator"]
