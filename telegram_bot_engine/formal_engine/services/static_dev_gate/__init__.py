"""StaticDevGate — AST + symbols + dataflow + taint rule engine."""

from .models import StaticFinding, StaticReport, AnalysisContext, ModuleInfo
from .service import analyze_project, verify_after_edit, plan_command_adds
from .engine import run_rules, analyze
from .context import build_context
from .dataflow import (
    analyze_source,
    analyze_module_flow,
    FunctionFlow,
    ModuleFlow,
    CFG,
    BasicBlock,
    Nullability,
    MaybeNoneUse,
    ResourceEvent,
)
from .symbols import SymbolTable, Symbol, build_symbol_table
from .rules.registry import all_rules, rules_by_id

__all__ = [
    "StaticFinding", "StaticReport", "AnalysisContext", "ModuleInfo",
    "analyze_project", "verify_after_edit", "plan_command_adds",
    "run_rules", "analyze", "build_context", "all_rules", "rules_by_id",
    "analyze_source", "analyze_module_flow", "FunctionFlow", "ModuleFlow",
    "CFG", "BasicBlock", "Nullability", "MaybeNoneUse", "ResourceEvent",
    "SymbolTable", "Symbol", "build_symbol_table",
]
