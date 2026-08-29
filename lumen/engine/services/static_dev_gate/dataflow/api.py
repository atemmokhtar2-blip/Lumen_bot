"""Public analyze_* entry points for module/function dataflow."""
from __future__ import annotations

import ast
from typing import Iterable

from .models import FunctionFlow, ModuleFlow, CFG, BasicBlock
from .cfg_builder import _CFGBuilder
from .visitor import _FlowVisitor

def analyze_function_flow(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    file: str,
    parent: str = "",
) -> FunctionFlow:
    qual = f"{parent}.{node.name}" if parent else node.name
    params: set[str] = set()
    for a in node.args.args + node.args.kwonlyargs:
        params.add(a.arg)
    if node.args.vararg:
        params.add(node.args.vararg.arg)
    if node.args.kwarg:
        params.add(node.args.kwarg.arg)
    params |= {"self", "cls"}

    # Phase 1: CFG
    cfg_builder = _CFGBuilder()
    cfg = cfg_builder.build(list(node.body))

    # Collect unreachable lines from CFG blocks
    cfg_unreachable: list[int] = []
    for b in cfg.blocks.values():
        if b.unreachable:
            for stmt in b.stmts:
                ln = getattr(stmt, "lineno", 0) or 0
                if ln:
                    cfg_unreachable.append(ln)

    # Phase 2–6: visitor
    v = _FlowVisitor(qual, params)
    for p in params:
        if p in (
            "message", "update", "query", "text", "user_input", "context",
            "callback_query", "args",
        ):
            v.tainted.add(p)
    for stmt in node.body:
        v.visit(stmt)

    unused: set[str] = set()
    for name in v._assigned_locals:
        if name.startswith("_"):
            continue
        if name not in v._used and name not in params:
            unused.add(name)

    # Resource leaks: still open, not via `with`
    leaks: list[tuple[str, str, int]] = []
    for name, (kind, ln, via_with) in v._open_resources.items():
        if not via_with:
            leaks.append((name, kind, ln))
    # anonymous opens without with also count
    for ev in v.resource_events:
        if ev.action == "open" and not ev.via_with and not ev.name:
            leaks.append(("", ev.kind, ev.lineno))

    # merge sequential + CFG unreachable
    all_unreach = sorted(set(v.unreachable_lines + cfg_unreachable))

    return FunctionFlow(
        qualname=qual,
        file=file,
        lineno=node.lineno,
        params=params,
        events=v.events,
        use_before_def=v.use_before_def,
        unused_locals=unused,
        dangerous_sinks=v.dangerous_sinks,
        tainted_to_sink=v.tainted_to_sink,
        has_await=v.has_await,
        is_async=isinstance(node, ast.AsyncFunctionDef),
        unreachable_lines=all_unreach,
        cfg=cfg,
        maybe_none_uses=v.maybe_none_uses,
        resource_events=v.resource_events,
        resource_leaks=leaks,
    )


def analyze_module_flow(tree: ast.AST, path: str) -> ModuleFlow:
    mod = ModuleFlow(path=path)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            mod.functions.append(analyze_function_flow(node, path))
        elif isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    mod.functions.append(
                        analyze_function_flow(item, path, parent=node.name)
                    )
    return mod


def analyze_source(source: str, path: str = "<src>") -> ModuleFlow | None:
    try:
        tree = ast.parse(source, filename=path)
    except SyntaxError:
        return None
    return analyze_module_flow(tree, path)
