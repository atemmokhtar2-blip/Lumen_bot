"""
StaticAnalyzer — Specification 039 (ULTRA CRITICAL)

Performs static analysis without executing code.
Produces issues, repair suggestions, dependency edges and risks.
Does not auto-fix; only suggests for downstream engines.
"""

from __future__ import annotations

import ast
import logging
import re
import uuid
from typing import Dict, List, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    AnalyzedUnit, StaticIssue, RepairSuggestion, DependencyEdge, RiskItem,
    SEVERITY_CRITICAL, SEVERITY_HIGH, SEVERITY_MEDIUM, SEVERITY_LOW, SEVERITY_INFO,
    STATUS_OPEN, STATUS_SUGGESTED,
    ISSUE_SYNTAX, ISSUE_PARSE, ISSUE_UNDEFINED_VAR, ISSUE_MISSING_IMPORT,
    ISSUE_UNREACHABLE, ISSUE_INFINITE_LOOP, ISSUE_DEAD_BRANCH,
    ISSUE_UNINITIALIZED, ISSUE_LAYER_BREAK, ISSUE_LONG_METHOD, ISSUE_LARGE_CLASS,
    ISSUE_LONG_PARAMS, ISSUE_GOD_OBJECT, ISSUE_DUPLICATED, ISSUE_CIRCULAR_DEP,
    ISSUE_HIDDEN_COUPLING, ISSUE_UNSAFE_API, ISSUE_UNSAFE_PARSE,
    ISSUE_HEAVY_LOOP, ISSUE_MEMORY_WASTE, ISSUE_FEATURE_ENVY,
    MAX_METHOD_LINES, MAX_CLASS_METHODS, MAX_PARAMS,
)

_log = logging.getLogger("engine.static_analysis.analyzer")

_WHILE_TRUE = re.compile(r"""while\s+True\s*:""")
_EVAL_EXEC = re.compile(r"""\b(?:eval|exec)\s*\(""")
_PICKLE = re.compile(r"""\bpickle\.(?:loads?|load)\s*\(""")
_YAML_LOAD = re.compile(r"""yaml\.load\s*\(""")
_RANGE_LARGE = re.compile(r"""range\s*\(\s*(\d{5,})\s*\)""")
_DEF_PARAMS = re.compile(r"""def\s+(\w+)\s*\(([^)]*)\)""")


class StaticAnalyzer:
    """Heuristic + AST-based static analyzer."""

    def analyze(
        self,
        ref_data: GenericData,
        arch_data: GenericData,
        perf_data: GenericData,
        sec_data: GenericData,
        bl_data: GenericData,
    ) -> Tuple[
        List[AnalyzedUnit],
        List[StaticIssue],
        List[RepairSuggestion],
        List[DependencyEdge],
        List[RiskItem],
    ]:
        units: List[AnalyzedUnit] = []
        issues: List[StaticIssue] = []
        suggestions: List[RepairSuggestion] = []
        deps: List[DependencyEdge] = []
        risks: List[RiskItem] = []

        bodies = self._collect_bodies(ref_data, perf_data, sec_data, bl_data)
        defined_names: Set[str] = set()
        unit_codes: Dict[str, str] = {}

        for body in bodies:
            uid = str(body.get("unit_id") or body.get("method_id") or body.get("name") or uuid.uuid4())
            code = str(
                body.get("refactored_code")
                or body.get("optimized_code")
                or body.get("secured_code")
                or body.get("source_code")
                or body.get("code")
                or ""
            )
            class_name = str(body.get("class_name") or "")
            method_name = str(body.get("method_name") or body.get("name") or "")
            location = f"{class_name}.{method_name}" if class_name else method_name or uid
            unit_codes[uid] = code
            if class_name:
                defined_names.add(class_name)
            if method_name:
                defined_names.add(method_name)

            unit_issues: List[StaticIssue] = []
            syntax_ok = True

            # --- Syntax / parse ---
            if code.strip():
                try:
                    # Try wrapping method bodies for parse
                    to_parse = code
                    if code.lstrip().startswith("def ") or code.lstrip().startswith("async def "):
                        to_parse = code
                    elif code.lstrip().startswith("class "):
                        to_parse = code
                    else:
                        to_parse = "def __unit__():\n" + "\n".join(
                            "    " + ln if ln.strip() else ln for ln in code.splitlines()
                        )
                    ast.parse(to_parse)
                except SyntaxError as se:
                    syntax_ok = False
                    unit_issues.append(StaticIssue(
                        issue_id=str(uuid.uuid4())[:8],
                        issue_type=ISSUE_SYNTAX,
                        severity=SEVERITY_CRITICAL,
                        message=f"Syntax error: {se.msg}",
                        location=location,
                        unit_id=uid,
                        snippet=str(getattr(se, "text", "") or "")[:120],
                        category="syntax",
                        repair_hint="Fix syntax before continuing.",
                    ))
                except Exception as ex:
                    unit_issues.append(StaticIssue(
                        issue_id=str(uuid.uuid4())[:8],
                        issue_type=ISSUE_PARSE,
                        severity=SEVERITY_HIGH,
                        message=f"Parse issue: {ex}",
                        location=location,
                        unit_id=uid,
                        category="syntax",
                        repair_hint="Review code structure.",
                    ))

            if not code.strip():
                units.append(AnalyzedUnit(
                    unit_id=uid, class_name=class_name, method_name=method_name,
                    syntax_ok=True, notes="empty",
                ))
                continue

            # --- Code smells / size ---
            lines = [ln for ln in code.splitlines() if ln.strip()]
            if len(lines) > MAX_METHOD_LINES:
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_LONG_METHOD,
                    severity=SEVERITY_MEDIUM,
                    message=f"Long method: {len(lines)} lines.",
                    location=location, unit_id=uid, category="smell",
                    repair_hint="Extract Method (refactoring engine).",
                ))

            methods = re.findall(r"""^\s+def\s+\w+""", code, re.MULTILINE)
            if len(methods) > MAX_CLASS_METHODS:
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_LARGE_CLASS,
                    severity=SEVERITY_HIGH,
                    message=f"Large class: {len(methods)} methods.",
                    location=location, unit_id=uid, category="smell",
                    repair_hint="Extract Class.",
                ))
            if len(methods) > 20:
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_GOD_OBJECT,
                    severity=SEVERITY_HIGH,
                    message=f"Possible God Object ({len(methods)} methods).",
                    location=location, unit_id=uid, category="smell",
                    repair_hint="Split responsibilities.",
                ))

            for m in _DEF_PARAMS.finditer(code):
                params = [p.strip() for p in m.group(2).split(",") if p.strip() and p.strip() != "self"]
                if len(params) > MAX_PARAMS:
                    unit_issues.append(StaticIssue(
                        issue_id=str(uuid.uuid4())[:8],
                        issue_type=ISSUE_LONG_PARAMS,
                        severity=SEVERITY_MEDIUM,
                        message=f"{m.group(1)} has {len(params)} parameters.",
                        location=f"{location}.{m.group(1)}", unit_id=uid, category="smell",
                        repair_hint="Introduce parameter object.",
                    ))

            # --- Control flow ---
            if _WHILE_TRUE.search(code) and not re.search(r"""\bbreak\b""", code):
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_INFINITE_LOOP,
                    severity=SEVERITY_HIGH,
                    message="while True without visible break.",
                    location=location, unit_id=uid, category="control",
                    repair_hint="Add exit condition or break.",
                ))

            if re.search(r"""if\s+False\s*:""", code):
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_DEAD_BRANCH,
                    severity=SEVERITY_LOW,
                    message="Dead branch: if False.",
                    location=location, unit_id=uid, category="control",
                    repair_hint="Remove dead code.",
                ))

            if re.search(r"""raise\s+\w+.*\n\s+\w+""", code):
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_UNREACHABLE,
                    severity=SEVERITY_MEDIUM,
                    message="Possible unreachable code after raise.",
                    location=location, unit_id=uid, category="control",
                    repair_hint="Remove or restructure unreachable statements.",
                ))

            # --- Data flow heuristics ---
            if re.search(r"""=\s*None\b""", code) and re.search(r"""\.\w+\s*\(""", code):
                # weak null-use signal
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_UNINITIALIZED,
                    severity=SEVERITY_LOW,
                    message="None assignment near attribute/call use — verify initialization.",
                    location=location, unit_id=uid, category="data",
                    repair_hint="Ensure variables are initialized before use.",
                ))

            # --- Security re-check ---
            if _EVAL_EXEC.search(code):
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_UNSAFE_API,
                    severity=SEVERITY_CRITICAL,
                    message="eval/exec usage.",
                    location=location, unit_id=uid, category="security",
                    repair_hint="Remove eval/exec.",
                ))
            if _PICKLE.search(code):
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_UNSAFE_PARSE,
                    severity=SEVERITY_CRITICAL,
                    message="pickle load of potentially untrusted data.",
                    location=location, unit_id=uid, category="security",
                    repair_hint="Prefer json; never unpickle untrusted input.",
                ))
            if _YAML_LOAD.search(code):
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_UNSAFE_PARSE,
                    severity=SEVERITY_HIGH,
                    message="yaml.load without SafeLoader.",
                    location=location, unit_id=uid, category="security",
                    repair_hint="Use yaml.safe_load.",
                ))

            # --- Performance ---
            if _RANGE_LARGE.search(code):
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_HEAVY_LOOP,
                    severity=SEVERITY_MEDIUM,
                    message="Large range loop.",
                    location=location, unit_id=uid, category="performance",
                    repair_hint="Batch or use generators.",
                ))
            if code.count(".append(") > 5 and "for " in code:
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_MEMORY_WASTE,
                    severity=SEVERITY_LOW,
                    message="Multiple appends in loop — consider list comprehension.",
                    location=location, unit_id=uid, category="performance",
                    repair_hint="Use list comprehension where possible.",
                ))

            # --- Architecture layer heuristic ---
            if re.search(r"""(?:handler|bot|api|presentation)""", class_name or method_name, re.I):
                if re.search(r"""(?:cursor\.execute|sqlite3|psycopg|session\.query)""", code, re.I):
                    unit_issues.append(StaticIssue(
                        issue_id=str(uuid.uuid4())[:8],
                        issue_type=ISSUE_LAYER_BREAK,
                        severity=SEVERITY_CRITICAL,
                        message="Presentation/handler accesses database directly.",
                        location=location, unit_id=uid, category="architecture",
                        repair_hint="Route via service/repository layer.",
                    ))

            # --- Imports / missing ---
            imports = re.findall(r"""^(?:from|import)\s+([\w.]+)""", code, re.MULTILINE)
            for imp in imports:
                deps.append(DependencyEdge(
                    from_unit=uid, to_unit=imp.split(".")[0], kind="import",
                ))

            # Feature envy: many external attribute accesses
            external_dots = len(re.findall(r"""\b(?!self)\w+\.\w+""", code))
            if external_dots > 15:
                unit_issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_FEATURE_ENVY,
                    severity=SEVERITY_LOW,
                    message="Many external attribute accesses (feature envy signal).",
                    location=location, unit_id=uid, category="smell",
                    repair_hint="Move logic closer to the data owner.",
                ))

            issues.extend(unit_issues)
            crit = sum(1 for i in unit_issues if i.severity == SEVERITY_CRITICAL)
            units.append(AnalyzedUnit(
                unit_id=uid,
                class_name=class_name,
                method_name=method_name,
                source_code=code,
                issue_count=len(unit_issues),
                critical_count=crit,
                syntax_ok=syntax_ok,
                notes=f"issues={len(unit_issues)}",
            ))

            if unit_issues:
                suggestions.append(self._suggest(location, unit_issues))

        # Circular dependency from import graph among our units
        graph: Dict[str, Set[str]] = {}
        name_to_uid = {u.method_name or u.class_name: u.unit_id for u in units if (u.method_name or u.class_name)}
        for d in deps:
            graph.setdefault(d.from_unit, set()).add(d.to_unit)
        # simple cycle among unit ids only
        cycles = self._find_cycles({
            u.unit_id: {x for x in graph.get(u.unit_id, set()) if x in {uu.unit_id for uu in units}}
            for u in units
        })
        for cyc in cycles[:3]:
            issues.append(StaticIssue(
                issue_id=str(uuid.uuid4())[:8],
                issue_type=ISSUE_CIRCULAR_DEP,
                severity=SEVERITY_CRITICAL,
                message=f"Circular dependency: {' -> '.join(cyc)}",
                location=" -> ".join(cyc),
                category="dependency",
                repair_hint="Break cycle with interface or intermediate module.",
            ))
            for edge_from, edge_to in zip(cyc, cyc[1:]):
                deps.append(DependencyEdge(
                    from_unit=edge_from, to_unit=edge_to, kind="cycle", circular=True,
                ))

        # Hidden coupling: global usage
        for uid, code in unit_codes.items():
            if re.search(r"""\bglobal\s+\w+""", code):
                issues.append(StaticIssue(
                    issue_id=str(uuid.uuid4())[:8],
                    issue_type=ISSUE_HIDDEN_COUPLING,
                    severity=SEVERITY_HIGH,
                    message="global statement — hidden coupling.",
                    unit_id=uid, category="dependency",
                    repair_hint="Inject dependencies explicitly.",
                ))

        # Risks from critical issues
        open_crit = [i for i in issues if i.severity == SEVERITY_CRITICAL and i.status == STATUS_OPEN]
        if open_crit:
            risks.append(RiskItem(
                risk_id=str(uuid.uuid4())[:8],
                severity=SEVERITY_CRITICAL,
                title="Open critical static analysis issues",
                description=f"{len(open_crit)} critical issue(s) must be resolved.",
                related_issue_ids=[i.issue_id for i in open_crit],
            ))

        _log.info(
            "StaticAnalyzer: units=%d issues=%d suggestions=%d deps=%d",
            len(units), len(issues), len(suggestions), len(deps),
        )
        return units, issues, suggestions, deps, risks

    def self_verify(
        self, units: List[AnalyzedUnit], issues: List[StaticIssue]
    ) -> Tuple[bool, List[StaticIssue]]:
        open_crit = [
            i for i in issues
            if i.severity == SEVERITY_CRITICAL and i.status == STATUS_OPEN
        ]
        syntax_fail = [u for u in units if not u.syntax_ok]
        residual = list(open_crit)
        for u in syntax_fail:
            residual.append(StaticIssue(
                issue_id=str(uuid.uuid4())[:8],
                issue_type=ISSUE_SYNTAX,
                severity=SEVERITY_CRITICAL,
                message=f"Unit {u.unit_id} still has syntax errors.",
                unit_id=u.unit_id,
                category="syntax",
                repair_hint="Fix syntax.",
            ))
        return len(open_crit) == 0 and len(syntax_fail) == 0, residual

    def _collect_bodies(self, *datasets: GenericData) -> List[Dict]:
        bodies: List[Dict] = []
        seen: Set[str] = set()
        code_keys = (
            "refactored_code", "optimized_code", "secured_code",
            "source_code", "code", "original_code",
        )
        for data in datasets:
            if not data.available:
                continue
            for it in data.items or []:
                uid = str(it.get("unit_id") or it.get("method_id") or it.get("name") or "")
                if not uid or uid in seen:
                    continue
                seen.add(uid)
                code = ""
                for k in code_keys:
                    if it.get(k):
                        code = str(it[k])
                        break
                bodies.append({
                    "unit_id": uid,
                    "class_name": it.get("class_name", ""),
                    "method_name": it.get("method_name") or it.get("name") or "",
                    "source_code": code,
                    "refactored_code": it.get("refactored_code"),
                    "optimized_code": it.get("optimized_code"),
                    "secured_code": it.get("secured_code"),
                })
        return bodies

    def _suggest(self, target: str, unit_issues: List[StaticIssue]) -> RepairSuggestion:
        steps: List[str] = []
        types = {i.issue_type for i in unit_issues}
        for_engine = "code_refactoring"
        if ISSUE_SYNTAX in types or ISSUE_PARSE in types:
            steps.append("Fix syntax/parse errors first.")
            for_engine = "manual"
        if ISSUE_LONG_METHOD in types or ISSUE_LARGE_CLASS in types or ISSUE_GOD_OBJECT in types:
            steps.append("Apply Extract Method / Extract Class.")
            for_engine = "code_refactoring"
        if ISSUE_LAYER_BREAK in types:
            steps.append("Move infrastructure access behind service/repository.")
            for_engine = "architecture_compliance"
        if ISSUE_UNSAFE_API in types or ISSUE_UNSAFE_PARSE in types:
            steps.append("Remove unsafe APIs; use safe alternatives.")
            for_engine = "security_review"
        if ISSUE_HEAVY_LOOP in types or ISSUE_MEMORY_WASTE in types:
            steps.append("Optimize loops and allocations.")
            for_engine = "performance_optimization"
        if not steps:
            steps.append("Review and address reported static issues.")
        priority = SEVERITY_CRITICAL if any(
            i.severity == SEVERITY_CRITICAL for i in unit_issues
        ) else SEVERITY_HIGH
        return RepairSuggestion(
            suggestion_id=str(uuid.uuid4())[:8],
            issue_ids=[i.issue_id for i in unit_issues],
            target=target,
            description=f"Repair suggestions for {target}",
            steps=steps,
            priority=priority,
            for_engine=for_engine,
        )

    def _find_cycles(self, graph: Dict[str, Set[str]]) -> List[List[str]]:
        cycles: List[List[str]] = []
        visited: Set[str] = set()
        stack: List[str] = []

        def dfs(node: str) -> None:
            if node in stack:
                i = stack.index(node)
                cycles.append(stack[i:] + [node])
                return
            if node in visited:
                return
            visited.add(node)
            stack.append(node)
            for nxt in graph.get(node, ()):
                dfs(nxt)
            stack.pop()

        for n in list(graph.keys()):
            dfs(n)
        return cycles


__all__ = ["StaticAnalyzer"]
