"""
Chat AI layer — optional guidance / translation only.

Roles:
  - SpecTranslator: speech → structured specification JSON (translate only, no code)
  - SmartChat: optional guidance replies (must not write project code)

Code generation is handled exclusively by the zero-AI path (spec_core).
This package is never used by generate_bot for emitting project files.
"""

from .smart_chat import SmartChatResult, smart_chat_reply
from .spec_translator import TranslatorResult, translate_spec, prepare_formal_text

__all__ = [
    "SmartChatResult",
    "smart_chat_reply",
    "TranslatorResult",
    "translate_spec",
    "prepare_formal_text",
]
