"""Typed errors for the templates bounded context."""
from __future__ import annotations


class TemplatesError(Exception):
    """Base for templates plane."""

    code: str = "templates_error"

    def __init__(self, message: str = "", *, code: str | None = None) -> None:
        super().__init__(message or self.code)
        if code:
            self.code = code


class CatalogError(TemplatesError):
    code = "catalog_error"


class PolicyDenied(TemplatesError):
    """Launch rejected by policy — never a soft warning."""

    code = "policy_denied"

    def __init__(self, reason: str) -> None:
        super().__init__(reason, code="policy_denied")
        self.reason = reason


class StoreError(TemplatesError):
    code = "store_error"


class InvalidTemplateId(TemplatesError):
    code = "invalid_template_id"


__all__ = [
    "TemplatesError",
    "CatalogError",
    "PolicyDenied",
    "StoreError",
    "InvalidTemplateId",
]
