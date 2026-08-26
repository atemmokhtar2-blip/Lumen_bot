"""spec_core — shared capability registry + language understanding.

Deterministic generation (pipeline / builder / presets / infinite / coding)
has been purged from the product path. Cline SDK is the sole generation engine.

This package retains only modules still used by IR validation, chat UX, and
delivery personalization.
"""

from .registry import CAPABILITIES, by_category, get_capability, list_capabilities
from .schema import BotSpec

__all__ = [
    "BotSpec",
    "CAPABILITIES",
    "get_capability",
    "list_capabilities",
    "by_category",
]

# Soft stubs so old imports fail clearly instead of AttributeError on missing submodule
def build_from_spec(*_a, **_k):
    raise RuntimeError(
        "deterministic_engine_purged: build_from_spec removed; use Cline SDK path"
    )


class BuildResult:  # noqa: D101
    def __init__(self, *a, **k):
        raise RuntimeError("deterministic_engine_purged: BuildResult removed")


class BuilderSession:  # noqa: D101
    def __init__(self, *a, **k):
        raise RuntimeError("deterministic_engine_purged: BuilderSession removed")


def get_session(*_a, **_k):
    raise RuntimeError("deterministic_engine_purged: get_session removed")


def reset_session(*_a, **_k):
    raise RuntimeError("deterministic_engine_purged: reset_session removed")
