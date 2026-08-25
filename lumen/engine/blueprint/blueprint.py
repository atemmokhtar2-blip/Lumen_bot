"""
Blueprint data model.

This module defines every data class that together describe a Telegram
bot project.  Each class has a single responsibility:

* :class:`BotMeta` — high level identity and framework selection.
* :class:`CommandSpec` — a single bot command (e.g. ``/start``).
* :class:`HandlerSpec` — a message/callback/query handler.
* :class:`StateNode` — a node in a conversation state machine.
* :class:`ConversationSpec` — a complete conversation flow.
* :class:`DatabaseSpec` — persistence configuration.
* :class:`MiddlewareSpec` — a middleware component.
* :class:`IntegrationSpec` — an external integration (e.g. AI API).
* :class:`ProjectSpec` — the project-level metadata (name, version, deps).
* :class:`Blueprint` — the root container.

All classes are plain ``dataclasses`` so they are easy to serialise,
inspect, and validate.  They carry no logic — logic lives in the
engines that produce and consume them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Bot identity
# ---------------------------------------------------------------------------

@dataclass
class BotMeta:
    """High-level identity of the bot being generated."""

    name: str
    display_name: str
    description: str
    language: str = "python"
    language_version: str = "3.11"
    framework: str = "python-telegram-bot"
    bot_type: str = "general"  # e.g. "group_admin", "store", "ai_assistant"
    token_env_var: str = "BOT_TOKEN"


# ---------------------------------------------------------------------------
# Commands & handlers
# ---------------------------------------------------------------------------

@dataclass
class CommandSpec:
    """A single slash command exposed by the bot."""

    name: str
    description: str
    arguments: List[str] = field(default_factory=list)
    admin_only: bool = False
    group_only: bool = False
    response_type: str = "text"  # text | keyboard | media | file
    handler_reference: str = ""  # optional, generator fills if empty


@dataclass
class HandlerSpec:
    """A message or update handler."""

    name: str
    handler_type: str  # message | callback_query | inline_query | edited_message
    triggers: List[str] = field(default_factory=list)
    description: str = ""


# ---------------------------------------------------------------------------
# Conversations / state machines
# ---------------------------------------------------------------------------

@dataclass
class StateNode:
    """A node in a conversation state machine.

    Each node has a name, the expected input type, and the next state
    to transition to once the input is received.
    """

    name: str
    prompt: str
    expected_input: str = "text"  # text | photo | location | contact | any
    next_state: Optional[str] = None
    validator: Optional[str] = None  # name of a validation rule


@dataclass
class ConversationSpec:
    """A complete conversation flow."""

    name: str
    entry_command: str
    entry_state: str
    states: List[StateNode] = field(default_factory=list)
    exit_state: Optional[str] = None

    def state_names(self) -> List[str]:
        return [s.name for s in self.states]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

@dataclass
class DatabaseSpec:
    """Persistence configuration for the generated bot."""

    enabled: bool = False
    backend: str = "sqlite"  # sqlite | postgres | mongodb | json
    models: List[Dict[str, Any]] = field(default_factory=list)
    connection_string_env: str = "DATABASE_URL"


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------

@dataclass
class MiddlewareSpec:
    """A middleware component inserted into the update pipeline."""

    name: str
    description: str = ""
    priority: int = 100
    enabled: bool = True


# ---------------------------------------------------------------------------
# Integrations
# ---------------------------------------------------------------------------

@dataclass
class IntegrationSpec:
    """An external integration the bot relies on."""

    name: str
    kind: str  # ai_provider | downloader | payment | external_api
    description: str = ""
    env_vars: List[str] = field(default_factory=list)
    config: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Project metadata
# ---------------------------------------------------------------------------

@dataclass
class ProjectSpec:
    """Project-level metadata for the generated codebase."""

    name: str
    version: str = "0.1.0"
    author: str = ""
    description: str = ""
    python_version: str = "3.11"
    dependencies: List[str] = field(default_factory=list)
    dev_dependencies: List[str] = field(default_factory=list)
    license: str = "MIT"
    use_docker: bool = True
    use_env_file: bool = True


# ---------------------------------------------------------------------------
# Root blueprint
# ---------------------------------------------------------------------------

@dataclass
class Blueprint:
    """The complete, resolved description of a bot to generate.

    This is the single object handed to the generator engines.  Every
    generator reads only the parts it cares about.
    """

    meta: BotMeta
    project: ProjectSpec
    commands: List[CommandSpec] = field(default_factory=list)
    handlers: List[HandlerSpec] = field(default_factory=list)
    conversations: List[ConversationSpec] = field(default_factory=list)
    database: DatabaseSpec = field(default_factory=DatabaseSpec)
    middlewares: List[MiddlewareSpec] = field(default_factory=list)
    integrations: List[IntegrationSpec] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)

    # -- convenience -------------------------------------------------------

    @property
    def bot_name(self) -> str:
        return self.meta.name

    def command_names(self) -> List[str]:
        return [c.name for c in self.commands]

    def conversation_names(self) -> List[str]:
        return [c.name for c in self.conversations]

    def has_database(self) -> bool:
        return self.database.enabled and bool(self.database.models)

    def has_integrations(self) -> bool:
        return len(self.integrations) > 0


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
