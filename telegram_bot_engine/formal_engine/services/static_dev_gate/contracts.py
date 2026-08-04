"""
Design by Contract + Static Type Checking (stdlib `ast` only).

Contracts are derived from the code itself — not from fixed templates:
  - Type annotations on params / returns = type contracts
  - Leading asserts in function body = preconditions
  - Asserts immediately before return / at end of paths = postconditions
  - Annotation presence on public callables = contract completeness

Checks:
  - Missing annotations (public functions)
  - Return value incompatible with annotated return type (concrete cases)
  - Binary ops on clearly incompatible annotated names
  - Preconditions that are concretely unsatisfiable
  - Annotated param shadowed without re-annotation consistency

Z3 / full gradual typing can plug into TypeLattice later.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum


# ---------------------------------------------------------------------------
# Type lattice (lightweight — expandable)
# ---------------------------------------------------------------------------


class TypeTag(str, Enum):
    ANY = "Any"
    NONE = "None"
    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STR = "str"
    BYTES = "bytes"
    LIST = "list"
    DICT = "dict"
    SET = "set"
    TUPLE = "tuple"
    CALLABLE = "callable"
    UNKNOWN = "unknown"


# numeric widen
_NUMERIC = {TypeTag.INT, TypeTag.FLOAT, TypeTag.BOOL}


def _ann_to_tag(node: ast.AST | None) -> TypeTag:
    if node is None:
        return TypeTag.ANY
    if isinstance(node, ast.Name):
        mapping = {
            "int": TypeTag.INT,
            "float": TypeTag.FLOAT,
            "str": TypeTag.STR,
            "bool": TypeTag.BOOL,
            "bytes": TypeTag.BYTES,
            "list": TypeTag.LIST,
            "dict": TypeTag.DICT,
            "set": TypeTag.SET,
            "tuple": TypeTag.TUPLE,
            "None": TypeTag.NONE,
            "Any": TypeTag.ANY,
            "object": TypeTag.ANY,
        }
        return mapping.get(node.id, TypeTag.UNKNOWN)
    if isinstance(node, ast.Constant) and node.value is None:
        return TypeTag.NONE
    if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
        base = _ann_to_tag(node.value)
        return base if base != TypeTag.UNKNOWN else TypeTag.UNKNOWN
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        # X | Y union — treat as ANY for strict checks
        return TypeTag.ANY
    if isinstance(node, ast.Attribute):
        return TypeTag.UNKNOWN
    return TypeTag.UNKNOWN


def types_compatible(expected: TypeTag, actual: TypeTag) -> bool:
    if expected in (TypeTag.ANY, TypeTag.UNKNOWN) or actual in (TypeTag.ANY, TypeTag.UNKNOWN):
        return True
    if expected == actual:
        return True
    if expected == TypeTag.FLOAT and actual in _NUMERIC:
        return True
    if expected == TypeTag.INT and actual == TypeTag.BOOL:
        return True
    return False


def infer_expr_type(node: ast.AST, env: dict[str, TypeTag]) -> TypeTag:
    if isinstance(node, ast.Constant):
        v = node.value
        if v is None:
            return TypeTag.NONE
        if isinstance(v, bool):
            return TypeTag.BOOL
        if isinstance(v, int):
            return TypeTag.INT
        if isinstance(v, float):
            return TypeTag.FLOAT
        if isinstance(v, str):
            return TypeTag.STR
        if isinstance(v, bytes):
            return TypeTag.BYTES
        return TypeTag.UNKNOWN
    if isinstance(node, ast.Name):
        if node.id in ("True", "False"):
            return TypeTag.BOOL
        if node.id == "None":
            return TypeTag.NONE
        return env.get(node.id, TypeTag.UNKNOWN)
    if isinstance(node, ast.JoinedStr):
        return TypeTag.STR
    if isinstance(node, ast.List):
        return TypeTag.LIST
    if isinstance(node, ast.Dict):
        return TypeTag.DICT
    if isinstance(node, ast.Set):
        return TypeTag.SET
    if isinstance(node, ast.Tuple):
        return TypeTag.TUPLE
    if isinstance(node, ast.BinOp):
        left = infer_expr_type(node.left, env)
        right = infer_expr_type(node.right, env)
        if isinstance(node.op, (ast.Add,)):
            if left == TypeTag.STR or right == TypeTag.STR:
                if left == TypeTag.STR and right == TypeTag.STR:
                    return TypeTag.STR
                return TypeTag.UNKNOWN  # possible error
            if left in _NUMERIC and right in _NUMERIC:
                if TypeTag.FLOAT in (left, right):
                    return TypeTag.FLOAT
                return TypeTag.INT
        if isinstance(node.op, (ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod, ast.Pow)):
            if left in _NUMERIC and right in _NUMERIC:
                if isinstance(node.op, ast.Div) or TypeTag.FLOAT in (left, right):
                    return TypeTag.FLOAT
                return TypeTag.INT
        return TypeTag.UNKNOWN
    if isinstance(node, ast.UnaryOp):
        return infer_expr_type(node.operand, env)
    if isinstance(node, ast.Compare):
        return TypeTag.BOOL
    if isinstance(node, ast.BoolOp):
        return TypeTag.BOOL
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            ctor = {
                "int": TypeTag.INT, "float": TypeTag.FLOAT, "str": TypeTag.STR,
                "bool": TypeTag.BOOL, "list": TypeTag.LIST, "dict": TypeTag.DICT,
                "set": TypeTag.SET, "tuple": TypeTag.TUPLE, "bytes": TypeTag.BYTES,
            }
            return ctor.get(node.func.id, TypeTag.UNKNOWN)
        return TypeTag.UNKNOWN
    if isinstance(node, ast.IfExp):
        a = infer_expr_type(node.body, env)
        b = infer_expr_type(node.orelse, env)
        return a if a == b else TypeTag.UNKNOWN
    if isinstance(node, ast.Attribute):
        return TypeTag.UNKNOWN
    if isinstance(node, ast.Subscript):
        base = infer_expr_type(node.value, env)
        if base == TypeTag.STR:
            return TypeTag.STR
        return TypeTag.UNKNOWN
    return TypeTag.UNKNOWN


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class ContractFinding:
    kind: str  # missing_annotation | type_mismatch | bad_binop | unsat_precondition | ...
    severity: str
    lineno: int
    message: str
    qualname: str = ""
    evidence: str = ""


@dataclass
class ParamContract:
    name: str
    type_tag: TypeTag
    annotated: bool
    lineno: int = 0


@dataclass
class FunctionContract:
    qualname: str
    lineno: int
    params: list[ParamContract] = field(default_factory=list)
    return_type: TypeTag = TypeTag.ANY
    return_annotated: bool = False
    preconditions: list[ast.Assert] = field(default_factory=list)
    postconditions: list[ast.Assert] = field(default_factory=list)
    findings: list[ContractFinding] = field(default_factory=list)
    is_public: bool = True


@dataclass
class ContractModuleResult:
    path: str
    functions: list[FunctionContract] = field(default_factory=list)
    findings: list[ContractFinding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extract contracts from function AST
# ---------------------------------------------------------------------------


def _is_public(name: str) -> bool:
    return not name.startswith("_")


def _leading_asserts(body: list[ast.stmt]) -> list[ast.Assert]:
    out: list[ast.Assert] = []
    for stmt in body:
        if isinstance(stmt, ast.Assert):
            out.append(stmt)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
            continue  # docstring
        else:
            break
    return out


def _trailing_asserts_before_returns(body: list[ast.stmt]) -> list[ast.Assert]:
    """Asserts that appear immediately before a Return in the same block."""
    out: list[ast.Assert] = []
    for i, stmt in enumerate(body):
        if isinstance(stmt, ast.Assert):
            # look ahead for return
            if i + 1 < len(body) and isinstance(body[i + 1], ast.Return):
                out.append(stmt)
        if isinstance(stmt, ast.If):
            out.extend(_trailing_asserts_before_returns(list(stmt.body)))
            out.extend(_trailing_asserts_before_returns(list(stmt.orelse)))
    return out


def analyze_function_contracts(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    file: str,
    parent: str = "",
) -> FunctionContract:
    qual = f"{parent}.{node.name}" if parent else node.name
    public = _is_public(node.name) and (not parent or _is_public(parent.split(".")[-1]))

    fc = FunctionContract(
        qualname=qual,
        lineno=node.lineno,
        return_type=_ann_to_tag(node.returns),
        return_annotated=node.returns is not None,
        is_public=public,
    )

    env: dict[str, TypeTag] = {"self": TypeTag.ANY, "cls": TypeTag.ANY}

    # params
    all_args = list(node.args.args) + list(node.args.kwonlyargs)
    for a in all_args:
        if a.arg in ("self", "cls"):
            fc.params.append(ParamContract(a.arg, TypeTag.ANY, True, getattr(a, "lineno", 0) or 0))
            continue
        tag = _ann_to_tag(a.annotation)
        annotated = a.annotation is not None
        fc.params.append(ParamContract(
            a.arg, tag, annotated, getattr(a, "lineno", 0) or node.lineno,
        ))
        env[a.arg] = tag if annotated else TypeTag.UNKNOWN

    if node.args.vararg:
        env[node.args.vararg.arg] = TypeTag.TUPLE
    if node.args.kwarg:
        env[node.args.kwarg.arg] = TypeTag.DICT

    # skip docstring for leading asserts
    body = list(node.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]

    fc.preconditions = _leading_asserts(body)
    fc.postconditions = _trailing_asserts_before_returns(list(node.body))

    # --- missing annotations on public API ---
    if public:
        missing_params = [p for p in fc.params if p.name not in ("self", "cls") and not p.annotated]
        if missing_params:
            names = ", ".join(f"`{p.name}`" for p in missing_params[:5])
            fc.findings.append(ContractFinding(
                kind="missing_annotation",
                severity="info",
                lineno=node.lineno,
                message=f"عقد ناقص: معاملات بدون نوع في `{qual}`: {names}",
                qualname=qual,
                evidence="params",
            ))
        if not fc.return_annotated and node.name not in ("__init__", "__aenter__", "__aexit__"):
            fc.findings.append(ContractFinding(
                kind="missing_annotation",
                severity="info",
                lineno=node.lineno,
                message=f"عقد ناقص: لا يوجد نوع إرجاع في `{qual}`",
                qualname=qual,
                evidence="return",
            ))

    # --- walk body for type mismatches & bad binops ---
    for stmt in ast.walk(node):
        if isinstance(stmt, ast.Assign):
            if stmt.value is not None:
                actual = infer_expr_type(stmt.value, env)
                for t in stmt.targets:
                    if isinstance(t, ast.Name):
                        # if previously annotated via AnnAssign env keeps it
                        if t.id not in env or env[t.id] == TypeTag.UNKNOWN:
                            env[t.id] = actual
        if isinstance(stmt, ast.AnnAssign):
            tag = _ann_to_tag(stmt.annotation)
            if isinstance(stmt.target, ast.Name):
                env[stmt.target.id] = tag
                if stmt.value is not None:
                    actual = infer_expr_type(stmt.value, env)
                    if not types_compatible(tag, actual):
                        fc.findings.append(ContractFinding(
                            kind="type_mismatch",
                            severity="error",
                            lineno=stmt.lineno,
                            message=(
                                f"تعارض نوع: `{stmt.target.id}` معلّن `{tag.value}` "
                                f"لكن القيمة `{actual.value}` في `{qual}`"
                            ),
                            qualname=qual,
                            evidence=f"{tag.value}!={actual.value}",
                        ))
        if isinstance(stmt, ast.Return) and stmt.value is not None:
            actual = infer_expr_type(stmt.value, env)
            if fc.return_annotated and not types_compatible(fc.return_type, actual):
                fc.findings.append(ContractFinding(
                    kind="type_mismatch",
                    severity="error",
                    lineno=stmt.lineno,
                    message=(
                        f"إرجاع غير متوافق: متوقع `{fc.return_type.value}` "
                        f"وحصل `{actual.value}` في `{qual}`"
                    ),
                    qualname=qual,
                    evidence=f"return:{actual.value}",
                ))
        if isinstance(stmt, ast.BinOp):
            left_t = infer_expr_type(stmt.left, env)
            right_t = infer_expr_type(stmt.right, env)
            if isinstance(stmt.op, ast.Add):
                # str + non-str
                if left_t == TypeTag.STR and right_t not in (TypeTag.STR, TypeTag.ANY, TypeTag.UNKNOWN):
                    fc.findings.append(ContractFinding(
                        kind="bad_binop",
                        severity="error",
                        lineno=getattr(stmt, "lineno", 0) or node.lineno,
                        message=f"جمع غير متوافق: str + {right_t.value} في `{qual}`",
                        qualname=qual,
                        evidence="add",
                    ))
                elif right_t == TypeTag.STR and left_t not in (TypeTag.STR, TypeTag.ANY, TypeTag.UNKNOWN):
                    fc.findings.append(ContractFinding(
                        kind="bad_binop",
                        severity="error",
                        lineno=getattr(stmt, "lineno", 0) or node.lineno,
                        message=f"جمع غير متوافق: {left_t.value} + str في `{qual}`",
                        qualname=qual,
                        evidence="add",
                    ))
            if isinstance(stmt.op, (ast.Sub, ast.Mult, ast.Div, ast.FloorDiv, ast.Mod)):
                if left_t == TypeTag.STR or right_t == TypeTag.STR:
                    if not (isinstance(stmt.op, ast.Mult) and TypeTag.INT in (left_t, right_t)):
                        fc.findings.append(ContractFinding(
                            kind="bad_binop",
                            severity="warning",
                            lineno=getattr(stmt, "lineno", 0) or node.lineno,
                            message=f"عملية حسابية على str في `{qual}`",
                            qualname=qual,
                            evidence=type(stmt.op).__name__,
                        ))

    # --- concretely false preconditions ---
    for pre in fc.preconditions:
        if isinstance(pre.test, ast.Constant) and not pre.test.value:
            fc.findings.append(ContractFinding(
                kind="unsat_precondition",
                severity="error",
                lineno=pre.lineno,
                message=f"شرط مسبق مستحيل (assert False) في `{qual}`",
                qualname=qual,
                evidence="precondition",
            ))

    return fc


def analyze_module_contracts(tree: ast.AST, path: str) -> ContractModuleResult:
    result = ContractModuleResult(path=path)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fc = analyze_function_contracts(node, path)
            result.functions.append(fc)
            result.findings.extend(fc.findings)
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    fc = analyze_function_contracts(item, path, parent=node.name)
                    result.functions.append(fc)
                    result.findings.extend(fc.findings)
    return result


def analyze_source_contracts(source: str, path: str = "<src>") -> ContractModuleResult | None:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return None
    return analyze_module_contracts(tree, path)
