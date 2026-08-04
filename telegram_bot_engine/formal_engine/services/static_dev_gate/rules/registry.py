"""Central rule registry — append new Rule classes here to expand the gate."""

from __future__ import annotations

from .syntax_rule import SyntaxRule
from .handler_rule import HandlerConsistencyRule, ExpectedCommandsRule
from .import_rule import LocalImportRule
from .security_rule import HardcodedTokenRule
from .telegram_rule import TelegramEntryRule
from .quality_rule import EmptyExceptRule, BareExceptRule
from .dataflow_rule import (
    UseBeforeDefRule, UnusedLocalRule, DangerousSinkRule,
    TaintToSinkRule, AsyncNoAwaitRule,
    UnreachableCodeRule, MaybeNoneRule, ResourceLeakRule,
)
from .symbolic_rule import (
    SymbolicDivZeroRule, SymbolicAssertRule,
    SymbolicNoneAccessRule, SymbolicAlwaysRaiseRule,
)
from .pattern_rule import (
    HighComplexityRule, DuplicatedCodeRule, MissingExceptRule,
)

# Order = execution order (core first)
_RULE_CLASSES = [
    SyntaxRule,
    HandlerConsistencyRule,
    ExpectedCommandsRule,
    LocalImportRule,
    HardcodedTokenRule,
    TelegramEntryRule,
    EmptyExceptRule,
    BareExceptRule,
    UseBeforeDefRule,
    UnusedLocalRule,
    DangerousSinkRule,
    TaintToSinkRule,
    AsyncNoAwaitRule,
    UnreachableCodeRule,
    MaybeNoneRule,
    ResourceLeakRule,
    SymbolicDivZeroRule,
    SymbolicAssertRule,
    SymbolicNoneAccessRule,
    SymbolicAlwaysRaiseRule,
    HighComplexityRule,
    DuplicatedCodeRule,
    MissingExceptRule,
]


def all_rules(enabled_only: bool = True):
    rules = [cls() for cls in _RULE_CLASSES]
    if enabled_only:
        rules = [r for r in rules if r.meta.default_enabled]
    return rules


def rules_by_id() -> dict:
    return {r.meta.id: r for r in all_rules(enabled_only=False)}
