"""spec_core — shared capability registry, schema, and language understanding helpers.

Generation itself is performed exclusively by the Cline SDK path.
This package retains only modules still used by IR validation, capability
detection, chat UX, and delivery personalization.
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
