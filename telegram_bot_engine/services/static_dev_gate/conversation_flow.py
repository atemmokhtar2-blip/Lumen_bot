"""
Conversation / flow analysis — structural + symbolic over state machines.

Sources (text-grounded, no domain templates):
  1. program_contract.json → conversation_states / flows
  2. app/states.py → UserState enum + STATE_PROMPTS
  3. handlers that reference UserState / STATE_PROMPTS

Checks:
  - dangling next_state
  - unreachable states
  - empty prompts
  - contract states missing from states.py
  - symbolic exploration of transition paths (bounded)
  - cycles (info)
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FlowFinding:
    severity: str  # error | warning | info
    code: str
    message: str
    evidence: str = ""
    path: str = ""


@dataclass
class ConversationFlowReport:
    ok: bool
    findings: list[FlowFinding] = field(default_factory=list)
    states: list[str] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)
    paths_explored: int = 0
    coverage: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[FlowFinding]:
        return [f for f in self.findings if f.severity == "error"]


def _load_contract(root: Path) -> dict[str, Any] | None:
    p = root / "program_contract.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def _graph_from_contract(contract: dict[str, Any]) -> tuple[dict[str, str], dict[str, str | None]]:
    """name → prompt, name → next_state."""
    prompts: dict[str, str] = {}
    nexts: dict[str, str | None] = {}
    for st in contract.get("conversation_states") or []:
        name = (st.get("name") or "").strip()
        if not name:
            continue
        prompts[name] = (st.get("prompt") or "").strip()
        nxt = st.get("next_state")
        nexts[name] = (nxt.strip() if isinstance(nxt, str) and nxt.strip() else None)
    # also from flows.steps if conversation_states empty
    if not prompts:
        for fl in contract.get("flows") or []:
            fname = fl.get("name") or "main"
            steps = fl.get("steps") or []
            for s in steps:
                sid = s.get("id") or ""
                name = f"{fname}__{sid}"
                prompts[name] = (s.get("label") or s.get("action") or "").strip()
                nid = s.get("next_id")
                nexts[name] = f"{fname}__{nid}" if nid else None
    return prompts, nexts


def _graph_from_states_py(source: str) -> tuple[set[str], dict[str, str]]:
    """Parse UserState members + STATE_PROMPTS keys/values."""
    names: set[str] = set()
    prompts: dict[str, str] = {}
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return names, prompts

    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "UserState":
            for item in node.body:
                if isinstance(item, ast.Assign):
                    for t in item.targets:
                        if isinstance(t, ast.Name):
                            names.add(t.id)
                elif isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                    names.add(item.target.id)
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "STATE_PROMPTS" and isinstance(node.value, ast.Dict):
                    for k, v in zip(node.value.keys, node.value.values):
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            val = v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else ""
                            prompts[k.value] = val
                            names.add(k.value)
    return names, prompts


def _handlers_reference_states(root: Path) -> bool:
    handlers = root / "app" / "handlers"
    if not handlers.exists():
        return False
    for f in handlers.rglob("*.py"):
        try:
            src = f.read_text(encoding="utf-8")
        except Exception:
            continue
        if "UserState" in src or "STATE_PROMPTS" in src or "ud.get(\"state\"" in src or "ud.get('state'" in src:
            return True
    return False


def _symbolic_explore(
    nexts: dict[str, str | None],
    starts: list[str],
    max_paths: int = 64,
    max_depth: int = 24,
) -> tuple[int, set[str], list[str]]:
    """
    Bounded DFS/BFS over the state transition graph.
    Returns (paths_explored, reachable_states, cycle_examples).
    """
    reachable: set[str] = set()
    cycles: list[str] = []
    paths = 0
    if not starts:
        starts = list(nexts.keys())[:1]

    for start in starts:
        if paths >= max_paths:
            break
        stack: list[tuple[str, list[str]]] = [(start, [start])]
        while stack and paths < max_paths:
            node, trail = stack.pop()
            reachable.add(node)
            if len(trail) > max_depth:
                paths += 1
                continue
            nxt = nexts.get(node)
            if nxt is None:
                paths += 1
                continue
            if nxt not in nexts and nxt not in reachable:
                # dangling — still count path end
                paths += 1
                reachable.add(nxt)
                continue
            if nxt in trail:
                cycles.append(" → ".join(trail + [nxt]))
                paths += 1
                continue
            stack.append((nxt, trail + [nxt]))
        if not stack:
            paths = max(paths, 1)
    return paths, reachable, cycles[:5]


def analyze_conversation_flow(project_dir: str | Path) -> ConversationFlowReport:
    root = Path(project_dir)
    findings: list[FlowFinding] = []
    contract = _load_contract(root)
    prompts: dict[str, str] = {}
    nexts: dict[str, str | None] = {}

    if contract:
        prompts, nexts = _graph_from_contract(contract)

    states_py = root / "app" / "states.py"
    code_names: set[str] = set()
    code_prompts: dict[str, str] = {}
    if states_py.exists():
        code_names, code_prompts = _graph_from_states_py(states_py.read_text(encoding="utf-8"))

    # Merge graphs for exploration: prefer contract nexts, fall back code-only
    if not nexts and code_names:
        for n in code_names:
            nexts[n] = None
            prompts.setdefault(n, code_prompts.get(n, ""))

    all_states = sorted(set(nexts) | set(prompts) | code_names)
    edges = [(a, b) for a, b in nexts.items() if b]

    # empty project / no flows
    if not all_states:
        return ConversationFlowReport(
            ok=True,
            findings=[],
            states=[],
            edges=[],
            paths_explored=0,
            coverage={"states": 0, "has_contract_states": bool(contract and (contract.get("conversation_states") or contract.get("flows")))},
        )

    # dangling next
    for name, nxt in nexts.items():
        if nxt is None:
            continue
        if nxt not in nexts and nxt not in code_names and nxt not in prompts:
            findings.append(
                FlowFinding(
                    "error",
                    "dangling_next_state",
                    f"الحالة `{name}` تشير إلى `{nxt}` غير المعرّفة",
                    evidence=f"{name}->{nxt}",
                    path="program_contract.json",
                )
            )

    # empty prompts
    for name, prompt in prompts.items():
        if not prompt or len(prompt.strip()) < 2:
            findings.append(
                FlowFinding(
                    "warning",
                    "empty_state_prompt",
                    f"الحالة `{name}` بلا نص توجيهي (prompt)",
                    evidence=name,
                    path="program_contract.json",
                )
            )

    # contract vs states.py
    if states_py.exists() and prompts:
        missing = [n for n in prompts if n not in code_names and n not in code_prompts]
        # enum members often UPPER — compare normalized
        code_norm = {x.lower().replace("-", "_") for x in code_names} | {x.lower() for x in code_prompts}
        for n in prompts:
            nn = n.lower().replace("-", "_")
            if nn not in code_norm and n not in code_prompts:
                findings.append(
                    FlowFinding(
                        "error",
                        "state_missing_in_code",
                        f"حالة العقد `{n}` غير موجودة في app/states.py",
                        evidence=n,
                        path="app/states.py",
                    )
                )

    if prompts and not states_py.exists():
        findings.append(
            FlowFinding(
                "error",
                "states_module_missing",
                "العقد فيه conversation_states لكن app/states.py مفقود",
                path="app/states.py",
            )
        )

    # handlers should reference state machine when states exist
    if (prompts or code_names) and states_py.exists() and not _handlers_reference_states(root):
        findings.append(
            FlowFinding(
                "warning",
                "handlers_ignore_states",
                "يوجد states.py لكن handlers لا تشير إلى UserState/STATE_PROMPTS",
                path="app/handlers",
            )
        )

    # symbolic exploration
    starts = []
    for n in all_states:
        if n.endswith("__s1") or n.endswith("_s1") or "start" in n.lower() or n == all_states[0]:
            starts.append(n)
    if not starts and all_states:
        starts = [all_states[0]]
    paths, reachable, cycles = _symbolic_explore(nexts, starts)

    unreachable = [n for n in nexts if n not in reachable]
    for n in unreachable:
        findings.append(
            FlowFinding(
                "warning",
                "unreachable_state",
                f"حالة غير قابلة للوصول من نقطة البداية: `{n}`",
                evidence=n,
            )
        )

    for cyc in cycles:
        findings.append(
            FlowFinding(
                "info",
                "state_cycle",
                f"دورة في مسار الحالات: {cyc}",
                evidence=cyc,
            )
        )

    ok = not any(f.severity == "error" for f in findings)
    return ConversationFlowReport(
        ok=ok,
        findings=findings,
        states=all_states,
        edges=edges,
        paths_explored=paths,
        coverage={
            "states": len(all_states),
            "edges": len(edges),
            "reachable": len(reachable),
            "paths_explored": paths,
            "cycles": len(cycles),
        },
    )


def conversation_flow_findings_as_static(report: ConversationFlowReport) -> list[dict[str, Any]]:
    """Map to a simple dict list for pipeline meta / fidelity consumers."""
    return [
        {
            "severity": f.severity,
            "code": f.code,
            "message": f.message,
            "evidence": f.evidence,
            "path": f.path,
        }
        for f in report.findings
    ]
