"""
Chat AI layer — g4f ONLY lives here.

Roles:
  - SpecTranslator: speech → structured specification JSON (translate only, no code)
  - SmartChat: optional guidance (must not write code)

Never import this package from formal_engine internals.
Formal engine remains the only code generator.
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
