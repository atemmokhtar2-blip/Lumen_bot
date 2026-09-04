"""Conversation domain types."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Conversation:
    id: str
    user_id: int
    title: str = "محادثة جديدة"
    created_at: float = 0.0
    updated_at: float = 0.0
    is_active: bool = True
    summary: str = ""
    message_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "is_active": self.is_active,
            "summary": self.summary,
            "message_count": self.message_count,
        }


@dataclass
class Message:
    id: str
    conversation_id: str
    user_id: int
    role: str  # user | assistant | system
    content: str
    tokens: int = 0
    created_at: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "tokens": self.tokens,
            "created_at": self.created_at,
        }
