"""Dataflow analysis package — import-stable public API.

from lumen.engine.services.static_dev_gate.dataflow import analyze_source, analyze_module_flow, ...
"""
from __future__ import annotations

from .models import (
    Nullability,
    NameEvent,
    BasicBlock,
    CFG,
    MaybeNoneUse,
    ResourceEvent,
    FunctionFlow,
    ModuleFlow,
)
from .api import analyze_function_flow, analyze_module_flow, analyze_source

__all__ = [
    "Nullability",
    "NameEvent",
    "BasicBlock",
    "CFG",
    "MaybeNoneUse",
    "ResourceEvent",
    "FunctionFlow",
    "ModuleFlow",
    "analyze_function_flow",
    "analyze_module_flow",
    "analyze_source",
]
