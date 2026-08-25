"""Coding Engine — thin facade over emitters / validators / scaffolding.

Public API preserved for all existing imports:
  generate_files, write_project, and private helpers used by tests/pipeline.
"""
from __future__ import annotations

from .emitters import (
    generate_files,
    _emit_bootstrap_sh,
    _emit_flow_engine,
    _emit_market,
    _emit_generic_runtime,
    _emit_generic_runtime_data,
    _emit_i18n_service,
    _emit_gitignore,
    _emit_readme,
    _emit_quality_tests,
    _emit_env_example,
    _emit_db_slim,
)
from .validators import _repair_handler_imports, _ensure_referenced_service_stubs
from .scaffolding import write_project, _feature_services

__all__ = [
    "generate_files",
    "write_project",
    "_repair_handler_imports",
    "_ensure_referenced_service_stubs",
    "_feature_services",
    "_emit_bootstrap_sh",
    "_emit_flow_engine",
    "_emit_market",
    "_emit_generic_runtime",
    "_emit_generic_runtime_data",
    "_emit_i18n_service",
    "_emit_gitignore",
    "_emit_readme",
    "_emit_quality_tests",
    "_emit_env_example",
    "_emit_db_slim",
]
