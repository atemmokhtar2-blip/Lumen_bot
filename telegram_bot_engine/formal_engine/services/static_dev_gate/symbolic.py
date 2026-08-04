"""
Symbolic Execution foundation (stdlib only — Z3-ready later).

Explores control-flow paths with symbolic (unknown) values instead of
concrete inputs.  Bounded, deterministic, engineering-grade — not a
research full-program symbolic VM.

Detects along paths:
  - division / modulo by zero (divisor may be zero)
  - assert that can fail under some path condition
  - attribute / subscript on values that may be None
  - paths that always raise
  - contradictory path conditions (dead symbolic paths)

Designed to consume CFG from dataflow analysis and to accept a future
Z3 backend for constraint satisfiability without rewriting the explorer.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Limits — keep exploration tractable
# ---------------------------------------------------------------------------

MAX_PATHS = 64
MAX_DEPTH = 40
MAX_LOOP_UNROLL = 2


# ---------------------------------------------------------------------------
# Symbolic value lattice
# ---------------------------------------------------------------------------


class SymKind(str, Enum):
    CONCRETE = "concrete"   # known Python value
    SYMBOL = "symbol"       # unknown input / param
    NONE = "none"           # definite None
    UNKNOWN = "unknown"     # top — no information
    BOTTOM = "bottom"       # unreachable / error state


@dataclass(frozen=True)
class SymValue:
    kind: SymKind
    value: Any = None       # concrete payload or symbol name
    origin: str = ""        # param name / expression hint

    @staticmethod
    def concrete(v: Any, origin: str = "") -> "SymValue":
        if v is None:
            return SymValue(SymKind.NONE, None, origin)
        return SymValue(SymKind.CONCRETE, v, origin)

    @staticmethod
    def symbol(name: str) -> "SymValue":
        return SymValue(SymKind.SYMBOL, name, name)

    @staticmethod
    def unknown(origin: str = "") -> "SymValue":
        return SymValue(SymKind.UNKNOWN, None, origin)

    @staticmethod
    def none(origin: str = "") -> "SymValue":
        return SymValue(SymKind.NONE, None, origin)

    @property
    def is_none(self) -> bool:
        return self.kind == SymKind.NONE

    @property
    def may_be_none(self) -> bool:
        """
        True only when None is plausible from analysis — not for plain
        symbolic parameters (update/context), which caused noise on
        every `context.args` / `update.message` access.
        """
        return self.kind in (SymKind.NONE, SymKind.UNKNOWN)

    def may_be_zero(self) -> bool:
        if self.kind == SymKind.CONCRETE:
            return self.value == 0
        if self.kind in (SymKind.SYMBOL, SymKind.UNKNOWN):
            return True
        return False


# ---------------------------------------------------------------------------
# Path constraints (Z3-ready interface)
# ---------------------------------------------------------------------------


class PredOp(str, Enum):
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LE = "le"
    GT = "gt"
    GE = "ge"
    IS_NONE = "is_none"
    NOT_NONE = "not_none"
    TRUTHY = "truthy"
    FALSY = "falsy"


@dataclass(frozen=True)
class Predicate:
    op: PredOp
    left: SymValue
    right: SymValue | None = None

    def negate(self) -> "Predicate":
        mapping = {
            PredOp.EQ: PredOp.NE,
            PredOp.NE: PredOp.EQ,
            PredOp.LT: PredOp.GE,
            PredOp.LE: PredOp.GT,
            PredOp.GT: PredOp.LE,
            PredOp.GE: PredOp.LT,
            PredOp.IS_NONE: PredOp.NOT_NONE,
            PredOp.NOT_NONE: PredOp.IS_NONE,
            PredOp.TRUTHY: PredOp.FALSY,
            PredOp.FALSY: PredOp.TRUTHY,
        }
        return Predicate(mapping[self.op], self.left, self.right)

    def is_clearly_false(self) -> bool:
        """Lightweight unsat check without solver — concrete only."""
        if self.op == PredOp.IS_NONE:
            return self.left.kind == SymKind.CONCRETE
        if self.op == PredOp.NOT_NONE:
            return self.left.kind == SymKind.NONE
        if self.left.kind != SymKind.CONCRETE:
            return False
        if self.op == PredOp.TRUTHY:
            return not bool(self.left.value)
        if self.op == PredOp.FALSY:
            return bool(self.left.value)
        if self.right is None or self.right.kind != SymKind.CONCRETE:
            return False
        a, b = self.left.value, self.right.value
        try:
            if self.op == PredOp.EQ:
                return a != b
            if self.op == PredOp.NE:
                return a == b
            if self.op == PredOp.LT:
                return not (a < b)
            if self.op == PredOp.LE:
                return not (a <= b)
            if self.op == PredOp.GT:
                return not (a > b)
            if self.op == PredOp.GE:
                return not (a >= b)
        except TypeError:
            return False
        return False

    def is_clearly_true(self) -> bool:
        return self.negate().is_clearly_false()


@dataclass
class ConstraintStore:
    """
    Conjunction of predicates along a path.

    `satisfiable()` uses concrete reasoning now; a Z3 backend can replace
    the body later without changing PathState / explorer.
    """

    preds: list[Predicate] = field(default_factory=list)

    def add(self, p: Predicate) -> "ConstraintStore":
        return ConstraintStore(self.preds + [p])

    def satisfiable(self) -> bool:
        for p in self.preds:
            if p.is_clearly_false():
                return False
        # pairwise concrete contradictions (x == 1 ∧ x == 2)
        concretes: dict[str, Any] = {}
        for p in self.preds:
            if p.op == PredOp.EQ and p.left.kind == SymKind.SYMBOL and p.right and p.right.kind == SymKind.CONCRETE:
                name = str(p.left.value)
                if name in concretes and concretes[name] != p.right.value:
                    return False
                concretes[name] = p.right.value
            if p.op == PredOp.IS_NONE and p.left.kind == SymKind.SYMBOL:
                name = str(p.left.value)
                if name in concretes and concretes[name] is not None:
                    return False
        return True

    def summary(self) -> str:
        parts = []
        for p in self.preds[:8]:
            if p.op in (PredOp.IS_NONE, PredOp.NOT_NONE, PredOp.TRUTHY, PredOp.FALSY):
                parts.append(f"{p.left.origin or p.left.value}:{p.op.value}")
            else:
                r = p.right.origin or p.right.value if p.right else ""
                parts.append(f"{p.left.origin or p.left.value} {p.op.value} {r}")
        return " ∧ ".join(parts) if parts else "true"


# ---------------------------------------------------------------------------
# Path state & findings
# ---------------------------------------------------------------------------


@dataclass
class SymFinding:
    kind: str           # div_by_zero | assert_fail | none_access | always_raise | unsat_path
    severity: str       # error | warning | info
    lineno: int
    message: str
    path_id: int = 0
    path_condition: str = ""


@dataclass
class PathState:
    path_id: int
    env: dict[str, SymValue] = field(default_factory=dict)
    constraints: ConstraintStore = field(default_factory=ConstraintStore)
    depth: int = 0
    returned: bool = False
    raised: bool = False
    raise_lineno: int = 0
    findings: list[SymFinding] = field(default_factory=list)
    # loop counters keyed by lineno of For/While
    loop_hits: dict[int, int] = field(default_factory=dict)

    def clone(self, path_id: int) -> "PathState":
        return PathState(
            path_id=path_id,
            env=dict(self.env),
            constraints=ConstraintStore(list(self.constraints.preds)),
            depth=self.depth,
            returned=self.returned,
            raised=self.raised,
            raise_lineno=self.raise_lineno,
            findings=list(self.findings),
            loop_hits=dict(self.loop_hits),
        )

    def get(self, name: str) -> SymValue:
        return self.env.get(name, SymValue.unknown(name))

    def set(self, name: str, val: SymValue) -> None:
        self.env[name] = val


@dataclass
class SymbolicFunctionResult:
    qualname: str
    file: str
    lineno: int
    paths_explored: int = 0
    paths_truncated: int = 0
    findings: list[SymFinding] = field(default_factory=list)
    always_raises: bool = False
    path_summaries: list[str] = field(default_factory=list)


@dataclass
class SymbolicModuleResult:
    path: str
    functions: list[SymbolicFunctionResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Expression evaluator (symbolic)
# ---------------------------------------------------------------------------


def _const(node: ast.AST) -> SymValue | None:
    if isinstance(node, ast.Constant):
        return SymValue.concrete(node.value)
    if isinstance(node, ast.Name):
        if node.id in ("True", "False", "None"):
            mapping = {"True": True, "False": False, "None": None}
            return SymValue.concrete(mapping[node.id]) if node.id != "None" else SymValue.none()
    return None


def eval_expr(node: ast.AST, state: PathState) -> SymValue:
    c = _const(node)
    if c is not None:
        return c

    # Unwrap async / yield wrappers so inner div/attr analysis still runs
    if isinstance(node, ast.Await):
        return eval_expr(node.value, state)
    if isinstance(node, (ast.Yield, ast.YieldFrom)):
        if isinstance(node, ast.YieldFrom):
            return eval_expr(node.value, state) if node.value is not None else SymValue.unknown("yield")
        return eval_expr(node.value, state) if node.value is not None else SymValue.unknown("yield")

    if isinstance(node, ast.Name):
        return state.get(node.id)

    if isinstance(node, ast.Attribute):
        base = eval_expr(node.value, state)
        origin = f"{base.origin}.{node.attr}" if base.origin else node.attr
        # chain on symbolic params (update/context) stays symbolic — no noise
        if base.kind == SymKind.SYMBOL:
            return SymValue.symbol(origin)
        if base.is_none:
            state.findings.append(SymFinding(
                kind="none_access",
                severity="error",
                lineno=getattr(node, "lineno", 0) or 0,
                message=f"وصول لصفة `{node.attr}` على قيمة None",
                path_id=state.path_id,
                path_condition=state.constraints.summary(),
            ))
            return SymValue.none(origin)
        # UNKNOWN from .get / optional only
        if base.kind == SymKind.UNKNOWN and base.origin in (
            "get", "subscript", "none", "call", "ifexp",
        ):
            state.findings.append(SymFinding(
                kind="none_access",
                severity="warning",
                lineno=getattr(node, "lineno", 0) or 0,
                message=f"وصول لصفة `{node.attr}` على قيمة قد تكون None",
                path_id=state.path_id,
                path_condition=state.constraints.summary(),
            ))
        return SymValue.unknown(origin)

    if isinstance(node, ast.Subscript):
        base = eval_expr(node.value, state)
        if not isinstance(node.slice, ast.Slice):
            eval_expr(node.slice, state)
        if base.is_none:
            state.findings.append(SymFinding(
                kind="none_access",
                severity="error",
                lineno=getattr(node, "lineno", 0) or 0,
                message="فهرسة على قيمة None",
                path_id=state.path_id,
                path_condition=state.constraints.summary(),
            ))
        elif base.kind == SymKind.UNKNOWN and base.origin in (
            "get", "subscript", "none", "call", "ifexp",
        ):
            state.findings.append(SymFinding(
                kind="none_access",
                severity="warning",
                lineno=getattr(node, "lineno", 0) or 0,
                message="فهرسة على قيمة قد تكون None",
                path_id=state.path_id,
                path_condition=state.constraints.summary(),
            ))
        return SymValue.unknown("subscript")

    if isinstance(node, ast.BinOp):
        left = eval_expr(node.left, state)
        right = eval_expr(node.right, state)
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
            if right.may_be_zero():
                state.findings.append(SymFinding(
                    kind="div_by_zero",
                    severity="error",
                    lineno=getattr(node, "lineno", 0) or 0,
                    message="قسمة / باقي قسمة على قيمة قد تكون صفرًا",
                    path_id=state.path_id,
                    path_condition=state.constraints.summary(),
                ))
        # concrete fold
        if left.kind == SymKind.CONCRETE and right.kind == SymKind.CONCRETE:
            try:
                ops = {
                    ast.Add: lambda a, b: a + b,
                    ast.Sub: lambda a, b: a - b,
                    ast.Mult: lambda a, b: a * b,
                    ast.Div: lambda a, b: a / b if b != 0 else None,
                    ast.FloorDiv: lambda a, b: a // b if b != 0 else None,
                    ast.Mod: lambda a, b: a % b if b != 0 else None,
                }
                fn = ops.get(type(node.op))
                if fn is not None:
                    result = fn(left.value, right.value)
                    if result is None:
                        return SymValue.unknown("div0")
                    return SymValue.concrete(result)
            except Exception:
                pass
        return SymValue.unknown("binop")

    if isinstance(node, ast.UnaryOp):
        v = eval_expr(node.operand, state)
        if isinstance(node.op, ast.Not):
            if v.kind == SymKind.CONCRETE:
                return SymValue.concrete(not v.value)
            return SymValue.unknown("not")
        if isinstance(node.op, ast.USub) and v.kind == SymKind.CONCRETE:
            try:
                return SymValue.concrete(-v.value)
            except Exception:
                pass
        return SymValue.unknown("unary")

    if isinstance(node, ast.Compare):
        left = eval_expr(node.left, state)
        # only first comparator for constraint building
        if len(node.ops) >= 1 and len(node.comparators) >= 1:
            right = eval_expr(node.comparators[0], state)
            op = node.ops[0]
            if left.kind == SymKind.CONCRETE and right.kind == SymKind.CONCRETE:
                try:
                    cmp_map = {
                        ast.Eq: left.value == right.value,
                        ast.NotEq: left.value != right.value,
                        ast.Lt: left.value < right.value,
                        ast.LtE: left.value <= right.value,
                        ast.Gt: left.value > right.value,
                        ast.GtE: left.value >= right.value,
                        ast.Is: left.value is right.value,
                        ast.IsNot: left.value is not right.value,
                    }
                    if type(op) in cmp_map:
                        return SymValue.concrete(cmp_map[type(op)])
                except Exception:
                    pass
            # is None / is not None
            if isinstance(op, ast.Is) and right.is_none:
                if left.is_none:
                    return SymValue.concrete(True)
                if left.kind == SymKind.CONCRETE:
                    return SymValue.concrete(False)
            if isinstance(op, ast.IsNot) and right.is_none:
                if left.is_none:
                    return SymValue.concrete(False)
                if left.kind == SymKind.CONCRETE:
                    return SymValue.concrete(True)
        return SymValue.unknown("compare")

    if isinstance(node, ast.BoolOp):
        vals = [eval_expr(v, state) for v in node.values]
        if all(v.kind == SymKind.CONCRETE for v in vals):
            if isinstance(node.op, ast.And):
                return SymValue.concrete(all(v.value for v in vals))
            return SymValue.concrete(any(v.value for v in vals))
        # x or ["0"] → prefer concrete fallback so subscript is safe
        if isinstance(node.op, ast.Or):
            for v in reversed(vals):
                if v.kind == SymKind.CONCRETE and v.value not in (None, False, 0, ""):
                    return v
            return vals[-1] if vals else SymValue.unknown("boolop")
        if isinstance(node.op, ast.And):
            return vals[-1] if vals else SymValue.unknown("boolop")
        return SymValue.unknown("boolop")

    if isinstance(node, ast.IfExp):
        cond = eval_expr(node.test, state)
        if cond.kind == SymKind.CONCRETE:
            return eval_expr(node.body if cond.value else node.orelse, state)
        # both sides unknown merge
        eval_expr(node.body, state)
        eval_expr(node.orelse, state)
        return SymValue.unknown("ifexp")

    if isinstance(node, ast.Call):
        # method call on possibly-None: y.upper() / product.get(...)
        if isinstance(node.func, ast.Attribute):
            base = eval_expr(node.func.value, state)
            if base.is_none:
                state.findings.append(SymFinding(
                    kind="none_access",
                    severity="error",
                    lineno=getattr(node, "lineno", 0) or 0,
                    message=f"استدعاء `{node.func.attr}()` على قيمة None",
                    path_id=state.path_id,
                    path_condition=state.constraints.summary(),
                ))
            elif base.kind == SymKind.UNKNOWN and base.origin in (
                "get", "subscript", "none", "call", "ifexp",
            ):
                state.findings.append(SymFinding(
                    kind="none_access",
                    severity="warning",
                    lineno=getattr(node, "lineno", 0) or 0,
                    message=f"استدعاء `{node.func.attr}()` على قيمة قد تكون None",
                    path_id=state.path_id,
                    path_condition=state.constraints.summary(),
                ))
            # dict.get → UNKNOWN (maybe none) for downstream
            if node.func.attr == "get":
                for a in node.args:
                    eval_expr(a, state)
                for kw in node.keywords:
                    if kw.value is not None:
                        eval_expr(kw.value, state)
                return SymValue.unknown("get")
        else:
            eval_expr(node.func, state)
        for a in node.args:
            eval_expr(a, state)
        for kw in node.keywords:
            if kw.value is not None:
                eval_expr(kw.value, state)
        # known pure constructors — int() result may be zero
        if isinstance(node.func, ast.Name) and node.func.id in (
            "int", "str", "float", "bool", "list", "dict", "set", "tuple"
        ):
            return SymValue.unknown(node.func.id)
        return SymValue.unknown("call")

    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for elt in node.elts:
            eval_expr(elt, state)
        return SymValue.concrete([] if isinstance(node, ast.List) else ())

    if isinstance(node, ast.Dict):
        return SymValue.concrete({})

    if isinstance(node, ast.JoinedStr):
        return SymValue.unknown("fstring")

    return SymValue.unknown("expr")


def _predicate_from_test(test: ast.AST, state: PathState) -> Predicate:
    """Build a Predicate from an if/while test expression."""
    # if x is None
    if isinstance(test, ast.Compare) and len(test.ops) == 1 and len(test.comparators) == 1:
        left = eval_expr(test.left, state)
        right = eval_expr(test.comparators[0], state)
        op = test.ops[0]
        if isinstance(op, ast.Is) and right.is_none:
            return Predicate(PredOp.IS_NONE, left)
        if isinstance(op, ast.IsNot) and right.is_none:
            return Predicate(PredOp.NOT_NONE, left)
        op_map = {
            ast.Eq: PredOp.EQ, ast.NotEq: PredOp.NE,
            ast.Lt: PredOp.LT, ast.LtE: PredOp.LE,
            ast.Gt: PredOp.GT, ast.GtE: PredOp.GE,
        }
        if type(op) in op_map:
            return Predicate(op_map[type(op)], left, right)
    # general truthiness
    val = eval_expr(test, state)
    return Predicate(PredOp.TRUTHY, val)


def _apply_narrowing(pred: Predicate, state: PathState) -> None:
    """Update env based on a proven path constraint."""
    if pred.op == PredOp.IS_NONE and pred.left.kind == SymKind.SYMBOL:
        name = str(pred.left.value)
        state.set(name, SymValue.none(name))
    elif pred.op == PredOp.NOT_NONE and pred.left.kind == SymKind.SYMBOL:
        name = str(pred.left.value)
        # keep as symbol but mark not-none via concrete placeholder origin
        state.set(name, SymValue(SymKind.SYMBOL, name, name))
    elif pred.op == PredOp.EQ and pred.left.kind == SymKind.SYMBOL and pred.right and pred.right.kind == SymKind.CONCRETE:
        name = str(pred.left.value)
        state.set(name, SymValue.concrete(pred.right.value, name))


# ---------------------------------------------------------------------------
# Statement executor — path forking
# ---------------------------------------------------------------------------


class _PathExplorer:
    def __init__(self) -> None:
        self.paths: list[PathState] = []
        self._next_id = 0
        self.truncated = 0

    def _new_id(self) -> int:
        i = self._next_id
        self._next_id += 1
        return i

    def explore(
        self,
        body: list[ast.stmt],
        params: set[str],
    ) -> list[PathState]:
        init = PathState(path_id=self._new_id())
        for p in params:
            init.set(p, SymValue.symbol(p))
        self._exec_block(body, init)
        return self.paths

    def _finish(self, state: PathState) -> None:
        if len(self.paths) >= MAX_PATHS:
            self.truncated += 1
            return
        self.paths.append(state)

    def _exec_block(self, stmts: list[ast.stmt], state: PathState) -> None:
        if state.returned or state.raised:
            self._finish(state)
            return
        if state.depth > MAX_DEPTH:
            self.truncated += 1
            self._finish(state)
            return
        if not stmts:
            self._finish(state)
            return

        stmt = stmts[0]
        rest = stmts[1:]
        state.depth += 1
        ln = getattr(stmt, "lineno", 0) or 0

        if isinstance(stmt, ast.Assign):
            val = eval_expr(stmt.value, state)
            for t in stmt.targets:
                self._store(t, val, state)
            self._exec_block(rest, state)
            return

        if isinstance(stmt, ast.AnnAssign):
            if stmt.value is not None:
                val = eval_expr(stmt.value, state)
            else:
                val = SymValue.unknown()
            self._store(stmt.target, val, state)
            self._exec_block(rest, state)
            return

        if isinstance(stmt, ast.AugAssign):
            # read-modify-write roughly
            if isinstance(stmt.target, ast.Name):
                cur = state.get(stmt.target.id)
                rhs = eval_expr(stmt.value, state)
                if isinstance(stmt.op, (ast.Div, ast.FloorDiv, ast.Mod)) and rhs.may_be_zero():
                    state.findings.append(SymFinding(
                        kind="div_by_zero",
                        severity="error",
                        lineno=ln,
                        message="AugAssign قسمة على قيمة قد تكون صفرًا",
                        path_id=state.path_id,
                        path_condition=state.constraints.summary(),
                    ))
                state.set(stmt.target.id, SymValue.unknown(stmt.target.id))
            else:
                eval_expr(stmt.value, state)
            self._exec_block(rest, state)
            return

        if isinstance(stmt, ast.Return):
            if stmt.value is not None:
                eval_expr(stmt.value, state)
            state.returned = True
            self._finish(state)
            return

        if isinstance(stmt, ast.Raise):
            if stmt.exc is not None:
                eval_expr(stmt.exc, state)
            state.raised = True
            state.raise_lineno = ln
            self._finish(state)
            return

        if isinstance(stmt, ast.Assert):
            test_val = eval_expr(stmt.test, state)
            if test_val.kind == SymKind.CONCRETE and not test_val.value:
                state.findings.append(SymFinding(
                    kind="assert_fail",
                    severity="error",
                    lineno=ln,
                    message="assert يفشل حتمًا على هذا المسار",
                    path_id=state.path_id,
                    path_condition=state.constraints.summary(),
                ))
                state.raised = True
                state.raise_lineno = ln
                self._finish(state)
                return
            if test_val.kind != SymKind.CONCRETE:
                # may fail under some inputs
                state.findings.append(SymFinding(
                    kind="assert_fail",
                    severity="warning",
                    lineno=ln,
                    message="assert قد يفشل تحت مدخلات رمزية",
                    path_id=state.path_id,
                    path_condition=state.constraints.summary(),
                ))
            if stmt.msg is not None:
                eval_expr(stmt.msg, state)
            self._exec_block(rest, state)
            return

        if isinstance(stmt, ast.Expr):
            eval_expr(stmt.value, state)
            self._exec_block(rest, state)
            return

        if isinstance(stmt, ast.If):
            pred = _predicate_from_test(stmt.test, state)
            # then branch
            then_state = state.clone(self._new_id())
            then_cs = then_state.constraints.add(pred)
            if then_cs.satisfiable():
                then_state.constraints = then_cs
                _apply_narrowing(pred, then_state)
                self._exec_block(list(stmt.body) + rest, then_state)
            else:
                self.truncated += 1
            # else branch
            else_state = state.clone(self._new_id())
            neg = pred.negate()
            else_cs = else_state.constraints.add(neg)
            if else_cs.satisfiable():
                else_state.constraints = else_cs
                _apply_narrowing(neg, else_state)
                self._exec_block(list(stmt.orelse) + rest, else_state)
            else:
                self.truncated += 1
            return

        if isinstance(stmt, (ast.For, ast.While)):
            hits = state.loop_hits.get(ln, 0)
            if hits >= MAX_LOOP_UNROLL:
                # skip body, continue after loop
                self._exec_block(list(stmt.orelse) + rest, state)
                return
            # unbound path: enter loop once
            enter = state.clone(self._new_id())
            enter.loop_hits[ln] = hits + 1
            if isinstance(stmt, ast.For):
                eval_expr(stmt.iter, enter)
                if isinstance(stmt.target, ast.Name):
                    enter.set(stmt.target.id, SymValue.unknown(stmt.target.id))
                elif isinstance(stmt.target, (ast.Tuple, ast.List)):
                    for elt in stmt.target.elts:
                        if isinstance(elt, ast.Name):
                            enter.set(elt.id, SymValue.unknown(elt.id))
            else:
                pred = _predicate_from_test(stmt.test, enter)
                enter.constraints = enter.constraints.add(pred)
            self._exec_block(list(stmt.body) + [stmt] + rest, enter)
            # zero-iteration path
            skip = state.clone(self._new_id())
            if isinstance(stmt, ast.While):
                pred = _predicate_from_test(stmt.test, skip)
                skip.constraints = skip.constraints.add(pred.negate())
            self._exec_block(list(stmt.orelse) + rest, skip)
            return

        if isinstance(stmt, (ast.With, ast.AsyncWith)):
            for item in stmt.items:
                val = eval_expr(item.context_expr, state)
                if item.optional_vars is not None:
                    self._store(item.optional_vars, val, state)
            self._exec_block(list(stmt.body) + rest, state)
            return

        if isinstance(stmt, ast.Try):
            # conservative: execute body then handlers as separate forks
            body_state = state.clone(self._new_id())
            self._exec_block(list(stmt.body) + list(stmt.orelse) + list(stmt.finalbody) + rest, body_state)
            for h in stmt.handlers:
                hs = state.clone(self._new_id())
                if h.name:
                    hs.set(h.name, SymValue.unknown(h.name))
                self._exec_block(list(h.body) + list(stmt.finalbody) + rest, hs)
            return

        if isinstance(stmt, (ast.Pass, ast.Break, ast.Continue, ast.Import, ast.ImportFrom,
                             ast.Global, ast.Nonlocal, ast.Delete)):
            if isinstance(stmt, (ast.Break, ast.Continue)):
                # end this path segment
                self._finish(state)
                return
            self._exec_block(rest, state)
            return

        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            # nested defs: skip body (isolated)
            self._exec_block(rest, state)
            return

        # fallback
        self._exec_block(rest, state)

    def _store(self, target: ast.AST, val: SymValue, state: PathState) -> None:
        if isinstance(target, ast.Name):
            state.set(target.id, val)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for elt in target.elts:
                self._store(elt, SymValue.unknown("unpack"), state)
        elif isinstance(target, ast.Attribute):
            eval_expr(target.value, state)
        elif isinstance(target, ast.Subscript):
            eval_expr(target.value, state)
            if not isinstance(target.slice, ast.Slice):
                eval_expr(target.slice, state)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_function_symbolic(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    file: str,
    parent: str = "",
) -> SymbolicFunctionResult:
    qual = f"{parent}.{node.name}" if parent else node.name
    params: set[str] = set()
    for a in node.args.args + node.args.kwonlyargs:
        params.add(a.arg)
    if node.args.vararg:
        params.add(node.args.vararg.arg)
    if node.args.kwarg:
        params.add(node.args.kwarg.arg)

    explorer = _PathExplorer()
    paths = explorer.explore(list(node.body), params)

    findings: list[SymFinding] = []
    seen: set[tuple[str, int, str]] = set()
    for p in paths:
        for f in p.findings:
            key = (f.kind, f.lineno, f.message)
            if key in seen:
                continue
            seen.add(key)
            findings.append(f)

    raising = [p for p in paths if p.raised and not p.returned]
    normal = [p for p in paths if p.returned or not p.raised]
    always_raises = bool(paths) and len(normal) == 0 and len(raising) > 0

    if always_raises:
        ln = raising[0].raise_lineno or node.lineno
        findings.append(SymFinding(
            kind="always_raise",
            severity="error",
            lineno=ln,
            message=f"كل المسارات الرمزية في `{qual}` تنتهي بـ raise",
            path_condition="all paths",
        ))

    summaries = [p.constraints.summary() for p in paths[:12]]

    return SymbolicFunctionResult(
        qualname=qual,
        file=file,
        lineno=node.lineno,
        paths_explored=len(paths),
        paths_truncated=explorer.truncated,
        findings=findings,
        always_raises=always_raises,
        path_summaries=summaries,
    )


def analyze_module_symbolic(tree: ast.AST, path: str) -> SymbolicModuleResult:
    result = SymbolicModuleResult(path=path)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.functions.append(analyze_function_symbolic(node, path))
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result.functions.append(
                        analyze_function_symbolic(item, path, parent=node.name)
                    )
    return result


def analyze_source_symbolic(source: str, path: str = "<src>") -> SymbolicModuleResult | None:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return None
    return analyze_module_symbolic(tree, path)
