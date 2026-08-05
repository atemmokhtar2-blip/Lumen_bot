"""
Chat AI layer — g4f powered assistant for user guidance only.

STRICT RULES:
  - This package is the ONLY place allowed to import g4f.
  - Never import this package (or g4f) from formal_engine, engines, or generation paths.
  - Role: understand user intent, clarify, and route to the correct capability.
  - Never generates code, never edits files, never claims generation success.
"""

from .smart_chat import SmartChatResult, smart_chat_reply

__all__ = [
    "SmartChatResult",
    "smart_chat_reply",
]
