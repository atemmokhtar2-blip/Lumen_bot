"""spec_core — zero-AI deterministic bot generation from BotSpec."""

from .pipeline import BuildResult, build_from_spec
from .registry import CAPABILITIES, by_category, get_capability, list_capabilities
from .schema import BotSpec
from .builder import BuilderSession, get_session, reset_session

__all__ = [
    "BotSpec",
    "BuildResult",
    "build_from_spec",
    "CAPABILITIES",
    "get_capability",
    "list_capabilities",
    "by_category",
    "BuilderSession",
    "get_session",
    "reset_session",
]
