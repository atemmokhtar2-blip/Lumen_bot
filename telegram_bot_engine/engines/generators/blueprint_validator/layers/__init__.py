"""
Validation Layers package (Specification 005).

This package contains the six validation layers that the
:class:`~telegram_bot_engine.engines.generators.blueprint_validator.blueprint_validator_engine.BlueprintValidatorEngine`
runs against a :class:`ProjectBlueprint`.

Each layer is a small, focused, stateless validator that returns a
:class:`~telegram_bot_engine.engines.generators.blueprint_validator.validation_report.LayerResult`.
The engine orchestrates the layers, collects their results, and produces
the final :class:`BlueprintValidationReport`.

Layers
------
* :class:`Layer1BasicData` — Layer 1: validates the basic project
  identity (name, bot type, language, framework, database).
* :class:`Layer2Features` — Layer 2: validates that every feature is
  described, has a clear goal, and there are no duplicates.
* :class:`Layer3Relationships` — Layer 3: validates that every feature
  is connected to the elements it depends on.
* :class:`Layer4ExecutionPlan` — Layer 4: validates the execution plan
  (correct order, no missing phases, no illogical phases).
* :class:`Layer5Dependencies` — Layer 5: validates all dependencies are
  correct and there are no conflicts.
* :class:`Layer6Buildability` — Layer 6: validates that the project can
  actually be built and that all required information is present.
"""

from __future__ import annotations

from .layer1_basic_data import Layer1BasicData
from .layer2_features import Layer2Features
from .layer3_relationships import Layer3Relationships
from .layer4_execution_plan import Layer4ExecutionPlan
from .layer5_dependencies import Layer5Dependencies
from .layer6_buildability import Layer6Buildability

__all__ = [
    "Layer1BasicData",
    "Layer2Features",
    "Layer3Relationships",
    "Layer4ExecutionPlan",
    "Layer5Dependencies",
    "Layer6Buildability",
]
