"""spec_core — zero-AI deterministic bot generation from BotSpec."""

from .pipeline import BuildResult, build_from_spec
from .registry import CAPABILITIES, get_capability, list_capabilities
from .schema import BotSpec

__all__ = [
    "BotSpec",
    "BuildResult",
    "build_from_spec",
    "CAPABILITIES",
    "get_capability",
    "list_capabilities",
]
