#!/usr/bin/env python3
"""
Comprehensive verification of all 13 engines in the pipeline.

Checks:
1. Every engine is registered in the registry.
2. Every engine is registered in the manager with correct priority & deps.
3. The dependency chain is valid (no missing deps, no circular).
4. Every engine class imports and instantiates correctly.
5. Every engine has a valid execute() method.
6. The priorities are sequential and consistent.
7. The full pipeline queue can be built.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from telegram_bot_engine.core.bootstrap import bootstrap
from telegram_bot_engine.core.contracts import Engine
from telegram_bot_engine.core.context import GenerationContext
from telegram_bot_engine.core.result import StageResult
from telegram_bot_engine.registry import EngineRegistry
from telegram_bot_engine.manager import CoreEngineManager

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

registry, orchestrator, manager = bootstrap()

queue = manager.queue_order()

print("=" * 80)
print("ENGINE VERIFICATION REPORT")
print("=" * 80)

# ---------------------------------------------------------------------------
# 1. Count
# ---------------------------------------------------------------------------

EXPECTED = 13
actual = len(queue)
status = "PASS" if actual == EXPECTED else "FAIL"
print(f"\n1. Engine count: {actual} (expected {EXPECTED}) [{status}]")

if actual != EXPECTED:
    print("   MISMATCH — investigating...")
    for item in sorted(queue, key=lambda m: m.priority):
        print(f"     {item.priority:>3}  {item.engine_id}")

# ---------------------------------------------------------------------------
# 2. Full list with priorities and dependencies
# ---------------------------------------------------------------------------

print(f"\n2. Full engine chain (sorted by priority):")
print(f"   {'#':<4} {'Priority':<10} {'Engine ID':<28} {'Dependencies'}")
print(f"   {'-'*4} {'-'*10} {'-'*28} {'-'*40}")

for i, item in enumerate(sorted(queue, key=lambda m: m.priority), 1):
    deps = ", ".join(item.dependencies) if item.dependencies else "(none)"
    print(f"   {i:<4} {item.priority:<10} {item.engine_id:<28} {deps}")

# ---------------------------------------------------------------------------
# 3. Registry vs Manager consistency
# ---------------------------------------------------------------------------

print(f"\n3. Registry vs Manager consistency:")
reg_engines = set(e.name for e in registry.engines())
mgr_ids = set(item.engine_id for item in queue)

# The registry engine names vs manager engine_ids
# They should match (the engine_id is set at registration time)
print(f"   Registry engines: {len(reg_engines)}")
print(f"   Manager engines:  {len(mgr_ids)}")

# Check each manager engine exists in registry
missing_in_registry = []
for item in queue:
    found = False
    for e in registry.engines():
        if e.name == item.engine_id or e.name == item.engine_id.replace("_", ""):
            found = True
            break
    if not found:
        # Try by getting the engine directly
        eng = registry.get_engine(item.engine_id)
        if eng is None:
            missing_in_registry.append(item.engine_id)

if missing_in_registry:
    print(f"   [FAIL] Engines in manager but NOT in registry: {missing_in_registry}")
else:
    print(f"   [PASS] All manager engines are in the registry")

# ---------------------------------------------------------------------------
# 4. Dependency validation — no missing, no circular
# ---------------------------------------------------------------------------

print(f"\n4. Dependency validation:")

mgr_engine_ids = set(item.engine_id for item in queue)
dep_map = {item.engine_id: item.dependencies for item in queue}

# Check no missing dependencies
missing_deps = []
for eid, deps in dep_map.items():
    for dep in deps:
        if dep not in mgr_engine_ids:
            missing_deps.append((eid, dep))

if missing_deps:
    print(f"   [FAIL] Missing dependencies:")
    for eid, dep in missing_deps:
        print(f"     {eid} depends on '{dep}' which is not registered")
else:
    print(f"   [PASS] No missing dependencies")

# Check no circular dependencies (simple DFS)
def has_cycle(graph):
    visited = set()
    rec_stack = set()

    def dfs(node):
        visited.add(node)
        rec_stack.add(node)
        for neighbor in graph.get(node, []):
            if neighbor not in visited:
                if dfs(neighbor):
                    return True
            elif neighbor in rec_stack:
                return True
        rec_stack.discard(node)
        return False

    for node in graph:
        if node not in visited:
            if dfs(node):
                return True
    return False

if has_cycle(dep_map):
    print(f"   [FAIL] Circular dependency detected!")
else:
    print(f"   [PASS] No circular dependencies")

# Check dependency priorities are correct (a dependency must have lower priority)
print(f"\n5. Priority ordering (dependencies must run first):")
prio_map = {item.engine_id: item.priority for item in queue}
priority_issues = []
for eid, deps in dep_map.items():
    for dep in deps:
        if prio_map.get(dep, 999) >= prio_map[eid]:
            priority_issues.append((eid, dep, prio_map[eid], prio_map.get(dep)))

if priority_issues:
    print(f"   [FAIL] Priority issues:")
    for eid, dep, ep, dp in priority_issues:
        print(f"     {eid} (priority {ep}) depends on {dep} (priority {dp})")
else:
    print(f"   [PASS] All dependencies have lower priority than dependents")

# ---------------------------------------------------------------------------
# 6. Every engine has a valid execute() method
# ---------------------------------------------------------------------------

print(f"\n6. Engine execute() method verification:")
exec_issues = []
for item in queue:
    eng = registry.get_engine(item.engine_id)
    if eng is None:
        exec_issues.append((item.engine_id, "not in registry"))
        continue
    if not hasattr(eng, "execute"):
        exec_issues.append((item.engine_id, "no execute() method"))
        continue
    if not callable(getattr(eng, "execute")):
        exec_issues.append((item.engine_id, "execute is not callable"))

if exec_issues:
    print(f"   [FAIL] Execute issues:")
    for eid, issue in exec_issues:
        print(f"     {eid}: {issue}")
else:
    print(f"   [PASS] All 13 engines have valid execute() methods")

# ---------------------------------------------------------------------------
# 7. Engine class types
# ---------------------------------------------------------------------------

print(f"\n7. Engine class types:")
for item in sorted(queue, key=lambda m: m.priority):
    eng = registry.get_engine(item.engine_id)
    if eng is not None:
        print(f"   {item.priority:>3}  {item.engine_id:<28} -> {type(eng).__name__}")

# ---------------------------------------------------------------------------
# 8. Engine-to-spec mapping
# ---------------------------------------------------------------------------

print(f"\n8. Specification mapping:")
spec_map = {
    "analyzer": "Spec 002",
    "intent_parser": "Spec 002",
    "blueprint_composer": "Spec 004",
    "project_planner": "Spec 004",
    "blueprint_validator": "Spec 005",
    "structure_generator": "Spec 006",
    "component_detector": "Spec 007",
    "file_planner": "Spec 008",
    "dependency_resolver": "Spec 009",
    "project_context": "Spec 010",
    "intelligence_graph": "Spec 011",
    "requirement_intelligence": "Spec 012",
    "semantic_understanding": "Spec 013",
}

for item in sorted(queue, key=lambda m: m.priority):
    spec = spec_map.get(item.engine_id, "???")
    print(f"   {item.priority:>3}  {item.engine_id:<28} {spec}")

# ---------------------------------------------------------------------------
# 9. Gap analysis — are there any priority gaps?
# ---------------------------------------------------------------------------

print(f"\n9. Priority gap analysis:")
priorities = sorted([item.priority for item in queue])
print(f"   Priorities: {priorities}")

gaps = []
for i in range(len(priorities) - 1):
    diff = priorities[i+1] - priorities[i]
    if diff > 10:
        gaps.append((priorities[i], priorities[i+1], diff))

if gaps:
    print(f"   Priority gaps (>10):")
    for p1, p2, diff in gaps:
        print(f"     {p1} -> {p2} (gap of {diff})")
else:
    print(f"   No significant priority gaps")

# ---------------------------------------------------------------------------
# 10. Full chain visualization
# ---------------------------------------------------------------------------

print(f"\n10. Full dependency chain (execution order):")
print(f"    {'='*70}")

for item in sorted(queue, key=lambda m: m.priority):
    deps = dep_map[item.engine_id]
    if deps:
        dep_str = " <- ".join(deps)
        print(f"    [{item.priority:>3}] {item.engine_id:<26} (needs: {dep_str})")
    else:
        print(f"    [{item.priority:>3}] {item.engine_id:<26} (root — no dependencies)")

print(f"    {'='*70}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'='*80}")
all_pass = (
    actual == EXPECTED
    and not missing_in_registry
    and not missing_deps
    and not has_cycle(dep_map)
    and not priority_issues
    and not exec_issues
)
if all_pass:
    print(f"SUMMARY: ALL 13 ENGINES VERIFIED — COMPLETE & INTEGRATED")
else:
    print(f"SUMMARY: ISSUES FOUND — see above")
print(f"{'='*80}")
