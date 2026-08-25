"""
Validators package — components that verify generation artefacts.

Validators run after engines (or after the whole pipeline) and produce
:class:`~core.result.ValidationReport` objects.  They never raise on
warnings — only the pipeline decides whether to stop.
"""

from .blueprint_validator import BlueprintValidator
from .structure_validator import StructureValidator
from .base_validator import BaseValidator

__all__ = [
    "BlueprintValidator",
    "StructureValidator",
    "BaseValidator",
]
