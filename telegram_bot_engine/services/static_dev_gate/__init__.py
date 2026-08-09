"""StaticDevGate — unified static analysis: patterns + dataflow + contracts + symbolic."""

from .models import StaticFinding, StaticReport, AnalysisContext, ModuleInfo
from .service import analyze_project, verify_after_edit, plan_command_adds
from .engine import run_rules, analyze
from .context import build_context
from .pipeline import run_pipeline, analyze_unified, PipelineReport, PHASE_ORDER
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
from .symbolic import (
    analyze_source_symbolic,
    analyze_module_symbolic,
    analyze_function_symbolic,
    SymbolicFunctionResult,
    SymbolicModuleResult,
    SymValue,
    SymKind,
    Predicate,
    ConstraintStore,
    SymFinding,
)
from .patterns import (
    analyze_source_patterns,
    analyze_module_patterns,
    analyze_function_patterns,
    PatternModuleResult,
    FunctionPatternInfo,
    PatternFinding,
    cyclomatic_complexity,
    register_pattern,
)
from .contracts import (
    analyze_source_contracts,
    analyze_module_contracts,
    analyze_function_contracts,
    ContractModuleResult,
    FunctionContract,
    ContractFinding,
    TypeTag,
)
from .symbols import SymbolTable, Symbol, build_symbol_table
from .rules.registry import all_rules, rules_by_id

__all__ = [
    "StaticFinding", "StaticReport", "AnalysisContext", "ModuleInfo",
    "analyze_project", "verify_after_edit", "plan_command_adds",
    "run_rules", "analyze", "build_context", "all_rules", "rules_by_id",
    "run_pipeline", "analyze_unified", "PipelineReport", "PHASE_ORDER",
    "analyze_source", "analyze_module_flow", "FunctionFlow", "ModuleFlow",
    "CFG", "BasicBlock", "Nullability", "MaybeNoneUse", "ResourceEvent",
    "analyze_source_symbolic", "analyze_module_symbolic", "analyze_function_symbolic",
    "SymbolicFunctionResult", "SymbolicModuleResult",
    "SymValue", "SymKind", "Predicate", "ConstraintStore", "SymFinding",
    "analyze_source_patterns", "analyze_module_patterns", "analyze_function_patterns",
    "PatternModuleResult", "FunctionPatternInfo", "PatternFinding",
    "cyclomatic_complexity", "register_pattern",
    "analyze_source_contracts", "analyze_module_contracts", "analyze_function_contracts",
    "ContractModuleResult", "FunctionContract", "ContractFinding", "TypeTag",
    "SymbolTable", "Symbol", "build_symbol_table",
]
from .fidelity import check_project_fidelity, FidelityReport, fidelity_as_dict
from .conversation_flow import analyze_conversation_flow, ConversationFlowReport
from .final_gate import run_final_gate, FinalGateReport
