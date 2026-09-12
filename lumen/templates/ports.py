"""Ports (interfaces) for the templates bounded context — hexagonal boundary.

Application code depends only on these Protocols. Adapters (JSON catalog,
Redis/memory store) implement them. No bot, hosting, or Telegram imports.
"""
from __future__ import annotations

from typing import Protocol, Sequence, runtime_checkable

from lumen.templates.models import TemplateInstance, TemplateSpec


@runtime_checkable
class TemplateCatalogPort(Protocol):
    def list_enabled(self) -> Sequence[TemplateSpec]:
        ...

    def get(self, template_id: str) -> TemplateSpec | None:
        ...


@runtime_checkable
class TemplateStorePort(Protocol):
    def list_for_user(self, user_id: int) -> list[TemplateInstance]:
        ...

    def save_for_user(self, user_id: int, instances: list[TemplateInstance]) -> None:
        ...

    def atomic_reserve(
        self,
        user_id: int,
        instance: TemplateInstance,
        *,
        max_active: int,
        now: float,
    ) -> tuple[bool, str]:
        """Persist instance only if active count stays under max_active.

        Returns (ok, reason). Must be race-safe under concurrent writers.
        """
        ...


__all__ = ["TemplateCatalogPort", "TemplateStorePort"]
