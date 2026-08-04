"""
Control & Data Flow Analysis on Python AST (stdlib `ast` only).

Builds per-function:
  - definitions (assigns, params, imports in scope)
  - uses (Name Load)
  - conservative use-before-def
  - reaches of names into dangerous sinks (eval/exec/...)

Not a full research CFG — deterministic engineering analysis suitable as a
gate for generated Telegram bots and active-repo edits.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Iterable



_TAINT_SOURCE_ATTRS = {
    ("message", "text"),
    ("message", "caption"),
    ("query", "data"),
    ("update", "text"),
}
_TAINT_SOURCE_NAMES = {"user_input", "text", "raw", "payload", "data"}

_DANGEROUS_CALLS = {
    "eval",
    "exec",
    "compile",
    "__import__",
    "os.system",
    "os.popen",
    "subprocess.call",
    "subprocess.run",
    "subprocess.Popen",
    "pickle.loads",
    "pickle.load",
}


@dataclass
class NameEvent:
    name: str
    lineno: int
    kind: str  # def | use
    context: str = ""  # function qualname


@dataclass
class FunctionFlow:
    qualname: str
    file: str
    lineno: int
    params: set[str] = field(default_factory=set)
    events: list[NameEvent] = field(default_factory=list)
    use_before_def: list[tuple[str, int]] = field(default_factory=list)  # name, lineno
    unused_locals: set[str] = field(default_factory=set)
    dangerous_sinks: list[tuple[str, int, str]] = field(default_factory=list)  # call, line, detail
    # name that is tainted -> sink label, lineno
    tainted_to_sink: list[tuple[str, str, int]] = field(default_factory=list)
    has_await: bool = False
    is_async: bool = False
    unreachable_lines: list[int] = field(default_factory=list)


@dataclass
class ModuleFlow:
    path: str
    functions: list[FunctionFlow] = field(default_factory=list)


def _call_label(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_label(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    return ""


def _assign_targets(target: ast.AST) -> list[str]:
    names: list[str] = []
    if isinstance(target, ast.Name):
        names.append(target.id)
    elif isinstance(target, (ast.Tuple, ast.List)):
        for elt in target.elts:
            names.extend(_assign_targets(elt))
    elif isinstance(target, ast.Starred):
        names.extend(_assign_targets(target.value))
    return names


class _FlowVisitor(ast.NodeVisitor):
    """Linear + branch-conservative definite assignment inside one function."""

    def __init__(self, qualname: str, params: set[str]) -> None:
        self.qualname = qualname
        self.defined: set[str] = set(params)
        self.events: list[NameEvent] = []
        self.use_before_def: list[tuple[str, int]] = []
        self.dangerous_sinks: list[tuple[str, int, str]] = []
        self.tainted_to_sink: list[tuple[str, str, int]] = []
        self.tainted: set[str] = set()
        self.has_await = False
        self.unreachable_lines: list[int] = []
        self._used: set[str] = set()
        self._assigned_locals: set[str] = set()
        self._returned = False

    def _use(self, name: str, lineno: int) -> None:
        if name in ("True", "False", "None"):
            return
        self.events.append(NameEvent(name, lineno, "use", self.qualname))
        self._used.add(name)
        if name not in self.defined and not name.isupper():  # skip CONSTANT convention lightly
            # builtins often used without def — filter common builtins
            if name in _BUILTINS:
                return
            self.use_before_def.append((name, lineno))

    def _def(self, name: str, lineno: int) -> None:
        self.events.append(NameEvent(name, lineno, "def", self.qualname))
        self.defined.add(name)
        self._assigned_locals.add(name)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load):
            self._use(node.id, node.lineno)
        elif isinstance(node.ctx, (ast.Store, ast.Param)):
            self._def(node.id, node.lineno)

    def visit_arg(self, node: ast.arg) -> None:
        self._def(node.arg, getattr(node, "lineno", 0) or 0)

    def visit_Assign(self, node: ast.Assign) -> None:
        # evaluate value first (uses), then defs
        self.visit(node.value)
        tainted_value = False
        for n in ast.walk(node.value):
            if isinstance(n, ast.Name) and (n.id in self.tainted or n.id in _TAINT_SOURCE_NAMES):
                tainted_value = True
            if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name):
                if (n.value.id, n.attr) in _TAINT_SOURCE_ATTRS or n.value.id in self.tainted:
                    tainted_value = True
        for t in node.targets:
            for n in _assign_targets(t):
                self._def(n, node.lineno)
                if tainted_value:
                    self.tainted.add(n)
            self.visit(t)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self.visit(node.value)
        for n in _assign_targets(node.target):
            self._def(n, node.lineno)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        # read then write
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            self._use(node.target.id, node.lineno)
            self._def(node.target.id, node.lineno)
        else:
            self.visit(node.target)

    def visit_For(self, node: ast.For) -> None:
        self.visit(node.iter)
        for n in _assign_targets(node.target):
            self._def(n, node.lineno)
        for stmt in node.body:
            self.visit(stmt)
        for stmt in node.orelse:
            self.visit(stmt)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                for n in _assign_targets(item.optional_vars):
                    self._def(n, node.lineno)
        for stmt in node.body:
            self.visit(stmt)

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        before = set(self.defined)
        # then branch
        for stmt in node.body:
            self.visit(stmt)
        after_then = set(self.defined)
        self.defined = set(before)
        for stmt in node.orelse:
            self.visit(stmt)
        after_else = set(self.defined)
        # definite assign = intersection of branches (conservative)
        self.defined = before | (after_then & after_else)

    def visit_While(self, node: ast.While) -> None:
        self.visit(node.test)
        before = set(self.defined)
        for stmt in node.body:
            self.visit(stmt)
        after_body = set(self.defined)
        self.defined = set(before)
        for stmt in node.orelse:
            self.visit(stmt)
        after_else = set(self.defined)
        self.defined = before | (after_body & after_else)

    def visit_Call(self, node: ast.Call) -> None:
        label = _call_label(node.func)
        self.visit(node.func)
        for a in node.args:
            self.visit(a)
        for kw in node.keywords:
            if kw.value is not None:
                self.visit(kw.value)
        if label in _DANGEROUS_CALLS or any(label.endswith("." + d.split(".")[-1]) for d in _DANGEROUS_CALLS):
            detail = "call"
            # flag if any Name arg not a constant-looking
            risky = False
            for a in node.args:
                if isinstance(a, ast.Name):
                    risky = True
                    detail = f"arg={a.id}"
                elif isinstance(a, ast.Attribute):
                    risky = True
                    detail = f"attr={_call_label(a)}"
                elif isinstance(a, ast.JoinedStr):  # f-string
                    risky = True
                    detail = "f-string"
            if risky or label in ("eval", "exec"):
                self.dangerous_sinks.append((label, node.lineno, detail))
            # taint → sink
            for a in node.args:
                if isinstance(a, ast.Name) and a.id in self.tainted:
                    self.tainted_to_sink.append((a.id, label or "call", node.lineno))
                if isinstance(a, ast.Attribute):
                    base = a.value.id if isinstance(a.value, ast.Name) else ""
                    if base in self.tainted or (base, a.attr) in _TAINT_SOURCE_ATTRS:
                        self.tainted_to_sink.append((f"{base}.{a.attr}", label or "call", node.lineno))


    def visit_Attribute(self, node: ast.Attribute) -> None:
        self.visit(node.value)
        if isinstance(node.value, ast.Name):
            pair = (node.value.id, node.attr)
            if pair in _TAINT_SOURCE_ATTRS:
                # attribute load of user-controlled field — mark synthetic use
                self.tainted.add(node.value.id)
        if isinstance(node.ctx, ast.Load) and isinstance(node.value, ast.Name):
            if node.value.id in self.tainted:
                pass

    def visit_Await(self, node: ast.Await) -> None:
        self.has_await = True
        self.visit(node.value)

    def visit_Return(self, node: ast.Return) -> None:
        if node.value is not None:
            self.visit(node.value)
        self._returned = True

    def visit_Raise(self, node: ast.Raise) -> None:
        if node.exc is not None:
            self.visit(node.exc)
        self._returned = True

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # nested function: do not flatten into parent flow
        return

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return


def _load_builtins() -> set[str]:
    names: set[str] = set()
    b = __builtins__
    if isinstance(b, dict):
        names |= set(b.keys())
    else:
        names |= set(dir(b))
    names |= {
        "print", "len", "range", "list", "dict", "set", "tuple", "str", "int", "float",
        "bool", "type", "isinstance", "issubclass", "getattr", "setattr", "hasattr",
        "enumerate", "zip", "map", "filter", "sorted", "sum", "min", "max", "open",
        "eval", "exec", "compile", "__import__", "input", "iter", "next", "id",
        "Exception", "ValueError", "TypeError", "KeyError", "AttributeError",
        "RuntimeError", "StopIteration", "True", "False", "None", "object",
        "super", "property", "classmethod", "staticmethod", "BaseException",
        "asyncio", "contextlib",
    }
    return names


_BUILTINS = _load_builtins()


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
    # self/cls are defined
    params |= {"self", "cls"}

    v = _FlowVisitor(qual, params)
    for stmt in node.body:
        v.visit(stmt)

    unused = set()
    for name in v._assigned_locals:
        if name.startswith("_"):
            continue
        if name not in v._used and name not in params:
            unused.add(name)

    # seed taint from telegram-ish parameter names
    for p in params:
        if p in ("message", "update", "query", "text", "user_input"):
            v.tainted.add(p)

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
        unreachable_lines=v.unreachable_lines,
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
