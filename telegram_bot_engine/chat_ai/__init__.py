"""
Chat AI layer — Hugging Face only.

Roles:
  - SpecTranslator: speech → structured specification JSON (translate only, no code)
  - SmartChat: optional guidance (must not write code)

Never import this package from legacy formal path (removed) internals.
Formal engine remains the only code generator.
No g4f or third-party free AI clients.
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
