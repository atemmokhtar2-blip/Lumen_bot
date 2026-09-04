"""LLM package — agent model catalog + key pool.

Translate/chat facade and daily budget gate were removed (agent path owns LLM).
"""
from .model_catalog import (
    CATALOG,
    CatalogModel,
    available_models,
    catalog_snapshot,
    get_model,
    models_for_role,
)

__all__ = [
    "CatalogModel",
    "CATALOG",
    "get_model",
    "models_for_role",
    "available_models",
    "catalog_snapshot",
]
from . import foundry_router  # noqa: F401
