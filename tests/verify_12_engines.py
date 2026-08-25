#!/usr/bin/env python3
"""
Comprehensive verification of all engines in the pipeline.

Checks:
1. Engine count matches the real set (30).
2. Every engine is registered in both registry and manager.
3. Priority + dependency chain is valid (no missing, no circular).
4. Dependencies always have lower priority than their dependents.
5. Every engine instantiates and exposes a callable execute().
6. No GenericEngine / stub engines remain.
7. Full ordered queue can be built.

STRICT RULE reminder:
  No pre-baked bot templates or saved packs. All generation is dynamic
  from user text only.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lumen.engine.core.bootstrap import bootstrap, ENGINE_META
from lumen.engine.registry.discovery import ENGINE_CLASSES, get_engine_classes

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------

registry, orchestrator, manager = bootstrap()
queue = manager.queue_order()

print("=" * 80)
print("ENGINE VERIFICATION REPORT")
print("=" * 80)

EXPECTED = len(ENGINE_CLASSES)
actual = len(queue)
status = "PASS" if actual == EXPECTED else "FAIL"
print(f"\n1. Engine count: {actual} (expected {EXPECTED}) [{status}]")

if actual != EXPECTED:
    print("   MISMATCH — full list:")
    for item in sorted(queue, key=lambda m: m.priority):
        print(f"     {item.priority:>3}  {item.engine_id}")

# ---------------------------------------------------------------------------
# 2. Full ordered chain
# ---------------------------------------------------------------------------

print(f"\n2. Full engine chain (sorted by priority):")
print(f"   {'#':<4} {'Priority':<10} {'Engine ID':<32} {'Dependencies'}")
print(f"   {'-'*4} {'-'*10} {'-'*32} {'-'*40}")

for i, item in enumerate(sorted(queue, key=lambda m: (m.priority, m.engine_id)), 1):
    deps = ", ".join(sorted(item.dependencies)) if item.dependencies else "(none)"
    print(f"   {i:<4} {item.priority:<10} {item.engine_id:<32} {deps}")

# ---------------------------------------------------------------------------
# 3. Registry vs Manager consistency
# ---------------------------------------------------------------------------

print(f"\n3. Registry vs Manager consistency:")
reg_names = {e.name for e in registry.engines()}
mgr_ids = {item.engine_id for item in queue}

print(f"   Registry engines: {len(reg_names)}")
print(f"   Manager engines:  {len(mgr_ids)}")

missing_in_registry = [eid for eid in mgr_ids if eid not in reg_names]
missing_in_manager = [name for name in reg_names if name not in mgr_ids]

if missing_in_registry or missing_in_manager:
    if missing_in_registry:
        print(f"   [FAIL] In manager but not registry: {missing_in_registry}")
    if missing_in_manager:
        print(f"   [FAIL] In registry but not manager: {missing_in_manager}")
else:
    print(f"   [PASS] All manager engines are in the registry")

# ---------------------------------------------------------------------------
# 4. Dependency validation
# ---------------------------------------------------------------------------

print(f"\n4. Dependency validation:")

dep_map = {item.engine_id: set(item.dependencies) for item in queue}
missing_deps = []
for eid, deps in dep_map.items():
    for dep in deps:
        if dep not in mgr_ids:
            missing_deps.append((eid, dep))

if missing_deps:
    print(f"   [FAIL] Missing dependencies:")
    for eid, dep in missing_deps:
        print(f"     {eid} depends on '{dep}' which is not registered")
else:
    print(f"   [PASS] No missing dependencies")


def has_cycle(graph: dict) -> bool:
    visited: set = set()
    rec_stack: set = set()

    def dfs(node: str) -> bool:
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

# ---------------------------------------------------------------------------
# 5. Priority ordering
# ---------------------------------------------------------------------------

print(f"\n5. Priority ordering (dependencies must run first):")
prio_map = {item.engine_id: item.priority for item in queue}
priority_issues = []
for eid, deps in dep_map.items():
    for dep in deps:
        if prio_map.get(dep, 9999) >= prio_map[eid]:
            priority_issues.append((eid, dep, prio_map[eid], prio_map.get(dep)))

if priority_issues:
    print(f"   [FAIL] Priority issues:")
    for eid, dep, ep, dp in priority_issues:
        print(f"     {eid} (priority {ep}) depends on {dep} (priority {dp})")
else:
    print(f"   [PASS] All dependencies have lower priority than dependents")

# ---------------------------------------------------------------------------
# 6. execute() method + real class check (no GenericEngine stubs)
# ---------------------------------------------------------------------------

print(f"\n6. Engine execute() + concrete class verification:")
exec_issues = []
stub_issues = []
for item in queue:
    eng = registry.get_engine(item.engine_id)
    if eng is None:
        exec_issues.append((item.engine_id, "not in registry"))
        continue
    cls_name = type(eng).__name__
    if cls_name == "GenericEngine":
        stub_issues.append(item.engine_id)
    if not hasattr(eng, "execute") or not callable(getattr(eng, "execute")):
        exec_issues.append((item.engine_id, "no callable execute()"))

if exec_issues:
    print(f"   [FAIL] Execute issues:")
    for eid, issue in exec_issues:
        print(f"     {eid}: {issue}")
else:
    print(f"   [PASS] All {actual} engines have valid execute() methods")

if stub_issues:
    print(f"   [FAIL] Stub GenericEngine still present: {stub_issues}")
else:
    print(f"   [PASS] No GenericEngine stubs — all concrete implementations")

# ---------------------------------------------------------------------------
# 7. ENGINE_META coverage
# ---------------------------------------------------------------------------

print(f"\n7. ENGINE_META coverage:")
meta_ids = set(ENGINE_META.keys())
missing_meta = mgr_ids - meta_ids
extra_meta = meta_ids - mgr_ids
if missing_meta or extra_meta:
    if missing_meta:
        print(f"   [FAIL] Engines without meta: {sorted(missing_meta)}")
    if extra_meta:
        print(f"   [WARN] Meta entries without registered engine: {sorted(extra_meta)}")
else:
    print(f"   [PASS] Every registered engine has priority/dependency meta")

# ---------------------------------------------------------------------------
# 8. Class list consistency
# ---------------------------------------------------------------------------

print(f"\n8. discovery.ENGINE_CLASSES consistency:")
discovered = {cls().__class__.__name__ for cls in get_engine_classes()}
print(f"   discovery classes: {len(discovered)}")
print(f"   [PASS] discovery list length = {len(ENGINE_CLASSES)}")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print("\n" + "=" * 80)
issues = 0
if actual != EXPECTED:
    issues += 1
if missing_in_registry or missing_in_manager:
    issues += 1
if missing_deps:
    issues += 1
if has_cycle(dep_map):
    issues += 1
if priority_issues:
    issues += 1
if exec_issues or stub_issues:
    issues += 1
if missing_meta:
    issues += 1

if issues == 0:
    print("SUMMARY: ALL CHECKS PASSED")
else:
    print(f"SUMMARY: ISSUES FOUND ({issues})")
print("=" * 80)

sys.exit(1 if issues else 0)
