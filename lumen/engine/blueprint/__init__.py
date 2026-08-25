"""
Blueprint — the intermediate representation of a Telegram bot.

A blueprint is a fully resolved description of the bot to generate.  It
is produced by the composer engine from the user's natural-language
request and is consumed by the generator engines to materialise the
project on disk.

The blueprint is the *single contract* between the "understanding" side
of the engine (intent parsing + composition) and the "building" side
(generators + builders).  Keeping it explicit means generators never
parse free text — they read a structured blueprint.
"""

from .blueprint import (
    Blueprint,
    BotMeta,
    CommandSpec,
    HandlerSpec,
    StateNode,
    ConversationSpec,
    DatabaseSpec,
    MiddlewareSpec,
    IntegrationSpec,
    ProjectSpec,
)

__all__ = [
    "Blueprint",
    "BotMeta",
    "CommandSpec",
    "HandlerSpec",
    "StateNode",
    "ConversationSpec",
    "DatabaseSpec",
    "MiddlewareSpec",
    "IntegrationSpec",
    "ProjectSpec",
]
