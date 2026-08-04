"""
AST Pattern Matching — structural / semantic analysis (stdlib `ast` only).

No fixed code templates. Patterns are computed from the actual AST shape:
  - Cyclomatic complexity (decision points per function)
  - Structural duplication (DRY): normalized AST fingerprints of function bodies
  - Missing exception handling around risky operations
  - Extensible PatternDef registry for future semantic rules

Consumes the same ModuleInfo / tree as dataflow & symbolic — no re-parse required
when tree is already on the module.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import dataclass, field
from typing import Callable, Iterator


# ---------------------------------------------------------------------------
# Thresholds — tunable, not hard-coded business logic templates
# ---------------------------------------------------------------------------

CYCLOMATIC_WARN = 10
CYCLOMATIC_ERROR = 20
MIN_BODY_NODES_FOR_DUP = 8          # ignore tiny functions in DRY check
DUP_FINGERPRINT_PREFIX = 24        # hash prefix length for grouping


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@dataclass
class PatternFinding:
    kind: str          # high_complexity | duplicated_code | missing_except | ...
    severity: str      # error | warning | info
    lineno: int
    message: str
    qualname: str = ""
    evidence: str = ""
    metric: float = 0.0


@dataclass
class FunctionPatternInfo:
    qualname: str
    lineno: int
    cyclomatic: int = 1
    body_fingerprint: str = ""
    body_size: int = 0
    has_try: bool = False
    risky_calls: list[tuple[str, int]] = field(default_factory=list)  # label, lineno
    findings: list[PatternFinding] = field(default_factory=list)


@dataclass
class PatternModuleResult:
    path: str
    functions: list[FunctionPatternInfo] = field(default_factory=list)
    findings: list[PatternFinding] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Cyclomatic complexity — McCabe from AST decision nodes
# ---------------------------------------------------------------------------

_DECISION_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.ExceptHandler,
    ast.With,
    ast.AsyncWith,
    ast.Assert,
    ast.comprehension,  # list/dict/set/genexp
)


def cyclomatic_complexity(node: ast.AST) -> int:
    """
    McCabe-style complexity: 1 + number of decision points.
    Also counts boolean operators (and/or) as extra branches.
    """
    score = 1
    for child in ast.walk(node):
        if isinstance(child, _DECISION_NODES):
            score += 1
        elif isinstance(child, ast.BoolOp):
            # and/or with n values → n-1 branches
            score += max(0, len(child.values) - 1)
        elif isinstance(child, ast.IfExp):
            score += 1
        elif isinstance(child, ast.Match):
            score += max(1, len(child.cases))
    return score


# ---------------------------------------------------------------------------
# Structural fingerprint — normalized AST for DRY detection
# ---------------------------------------------------------------------------


def _normalize_node(node: ast.AST) -> str:
    """
    Strip names/constants to compare structure only.
    Functionally similar bodies share the same fingerprint.
    """
    typ = type(node).__name__

    if isinstance(node, ast.Name):
        return "Name"
    if isinstance(node, ast.Attribute):
        return f"Attr({_normalize_node(node.value)})"
    if isinstance(node, ast.Constant):
        # keep type of constant, not value (so 1 and 2 look alike)
        return f"Const({type(node.value).__name__})"
    if isinstance(node, ast.arg):
        return "arg"
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        # fingerprint body only — name is identity, not structure
        body_parts = [_normalize_node(s) for s in node.body]
        return f"Func[{','.join(body_parts)}]"
    if isinstance(node, ast.ClassDef):
        return f"Class[{','.join(_normalize_node(s) for s in node.body)}]"

    fields = []
    for field_name, value in ast.iter_fields(node):
        if field_name in ("lineno", "col_offset", "end_lineno", "end_col_offset",
                          "type_comment", "type_params"):
            continue
        if field_name in ("id", "name", "attr", "arg", "module", "level"):
            continue  # identity stripped
        if isinstance(value, ast.AST):
            fields.append(_normalize_node(value))
        elif isinstance(value, list):
            fields.append("[" + ",".join(
                _normalize_node(v) if isinstance(v, ast.AST) else repr(type(v).__name__)
                for v in value
            ) + "]")
        elif value is None or isinstance(value, (bool, int, float, str, bytes)):
            continue
        else:
            fields.append(type(value).__name__)
    return f"{typ}({','.join(fields)})"


def body_fingerprint(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, int]:
    """Return (hash, approximate node count) for the function body."""
    parts = [_normalize_node(s) for s in node.body]
    raw = ";".join(parts)
    size = sum(1 for _ in ast.walk(node))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:DUP_FINGERPRINT_PREFIX]
    return digest, size


# ---------------------------------------------------------------------------
# Risky operations that should usually sit under try/except
# ---------------------------------------------------------------------------

_RISKY_CALL_NAMES = {
    "open",
    "int",
    "float",
    "json.loads",
    "json.load",
    "yaml.load",
    "yaml.safe_load",
    "requests.get",
    "requests.post",
    "requests.put",
    "requests.delete",
    "urllib.request.urlopen",
    "urlopen",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_output",
    "os.remove",
    "os.unlink",
    "shutil.rmtree",
    "socket.connect",
}


def _call_label(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_label(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _lineno_in_try(lineno: int, try_ranges: list[tuple[int, int]]) -> bool:
    for start, end in try_ranges:
        if start <= lineno <= end:
            return True
    return False


def _try_ranges(fn_node: ast.AST) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for child in ast.walk(fn_node):
        if isinstance(child, ast.Try):
            start = getattr(child, "lineno", 0) or 0
            # end = last lineno in body/handlers/finally
            end = start
            for sub in ast.walk(child):
                ln = getattr(sub, "lineno", 0) or 0
                if ln > end:
                    end = ln
            ranges.append((start, end))
    return ranges


def collect_risky_calls(
    fn_node: ast.FunctionDef | ast.AsyncFunctionDef,
) -> tuple[bool, list[tuple[str, int]]]:
    """Return (has_try, list of risky calls not covered by try)."""
    ranges = _try_ranges(fn_node)
    has_try = bool(ranges)
    risky: list[tuple[str, int]] = []
    for child in ast.walk(fn_node):
        if not isinstance(child, ast.Call):
            continue
        label = _call_label(child.func)
        # match full or suffix (requests.get, .get less specific — require known set)
        matched = label in _RISKY_CALL_NAMES
        if not matched:
            for known in _RISKY_CALL_NAMES:
                if label.endswith("." + known.split(".")[-1]) and known.count(".") >= 1:
                    if label.endswith(known) or label == known:
                        matched = True
                        break
                if label == known:
                    matched = True
                    break
        if not matched:
            continue
        ln = getattr(child, "lineno", 0) or 0
        if not _lineno_in_try(ln, ranges):
            risky.append((label, ln))
    return has_try, risky


# ---------------------------------------------------------------------------
# Per-function analysis
# ---------------------------------------------------------------------------


def analyze_function_patterns(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    file: str,
    parent: str = "",
) -> FunctionPatternInfo:
    qual = f"{parent}.{node.name}" if parent else node.name
    info = FunctionPatternInfo(qualname=qual, lineno=node.lineno)

    # complexity
    info.cyclomatic = cyclomatic_complexity(node)
    if info.cyclomatic >= CYCLOMATIC_ERROR:
        info.findings.append(PatternFinding(
            kind="high_complexity",
            severity="error",
            lineno=node.lineno,
            message=f"تعقيد دائري مرتفع جدًا ({info.cyclomatic}) في `{qual}`",
            qualname=qual,
            evidence=f"cyclomatic={info.cyclomatic}",
            metric=float(info.cyclomatic),
        ))
    elif info.cyclomatic >= CYCLOMATIC_WARN:
        info.findings.append(PatternFinding(
            kind="high_complexity",
            severity="warning",
            lineno=node.lineno,
            message=f"تعقيد دائري مرتفع ({info.cyclomatic}) في `{qual}`",
            qualname=qual,
            evidence=f"cyclomatic={info.cyclomatic}",
            metric=float(info.cyclomatic),
        ))

    # fingerprint
    fp, size = body_fingerprint(node)
    info.body_fingerprint = fp
    info.body_size = size

    # missing except around risky calls
    has_try, risky = collect_risky_calls(node)
    info.has_try = has_try
    info.risky_calls = risky
    for label, ln in risky:
        info.findings.append(PatternFinding(
            kind="missing_except",
            severity="warning",
            lineno=ln,
            message=f"استدعاء خطر `{label}` بدون try/except في `{qual}`",
            qualname=qual,
            evidence=label,
        ))

    return info


def analyze_module_patterns(tree: ast.AST, path: str) -> PatternModuleResult:
    result = PatternModuleResult(path=path)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.functions.append(analyze_function_patterns(node, path))
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    result.functions.append(
                        analyze_function_patterns(item, path, parent=node.name)
                    )

    # DRY: group by fingerprint
    groups: dict[str, list[FunctionPatternInfo]] = {}
    for fn in result.functions:
        if fn.body_size < MIN_BODY_NODES_FOR_DUP:
            continue
        if not fn.body_fingerprint:
            continue
        groups.setdefault(fn.body_fingerprint, []).append(fn)

    for fp, members in groups.items():
        if len(members) < 2:
            continue
        names = ", ".join(f"`{m.qualname}`" for m in members[:5])
        for m in members:
            finding = PatternFinding(
                kind="duplicated_code",
                severity="warning",
                lineno=m.lineno,
                message=f"تكرار هيكلي (DRY): {names}",
                qualname=m.qualname,
                evidence=fp,
            )
            m.findings.append(finding)
            result.findings.append(finding)

    for fn in result.functions:
        result.findings.extend(
            f for f in fn.findings if f.kind != "duplicated_code"
        )

    return result


def analyze_source_patterns(source: str, path: str = "<src>") -> PatternModuleResult | None:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return None
    return analyze_module_patterns(tree, path)


# ---------------------------------------------------------------------------
# Extensible pattern registry (future semantic patterns plug in here)
# ---------------------------------------------------------------------------


@dataclass
class PatternDef:
    id: str
    description_ar: str
    # predicate: (function_node, FunctionPatternInfo) -> list[PatternFinding]
    check: Callable[
        [ast.FunctionDef | ast.AsyncFunctionDef, FunctionPatternInfo],
        list[PatternFinding],
    ]


_EXTRA_PATTERNS: list[PatternDef] = []


def register_pattern(pattern: PatternDef) -> None:
    """Add a custom structural pattern without modifying the core engine."""
    _EXTRA_PATTERNS.append(pattern)


def extra_patterns() -> list[PatternDef]:
    return list(_EXTRA_PATTERNS)
