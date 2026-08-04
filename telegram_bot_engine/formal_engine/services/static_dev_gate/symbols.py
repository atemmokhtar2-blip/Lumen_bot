"""Module-level symbol table from AST — foundation for scoped name resolution."""

from __future__ import annotations

import ast
from dataclasses import dataclass, field


@dataclass
class Symbol:
    name: str
    kind: str  # function | async_function | class | import | assign | param
    lineno: int
    qualname: str = ""


@dataclass
class SymbolTable:
    """Flat + nested symbols for one module file."""
    path: str
    globals: dict[str, Symbol] = field(default_factory=dict)
    # function qualname -> local symbols
    locals: dict[str, dict[str, Symbol]] = field(default_factory=dict)

    def has_global(self, name: str) -> bool:
        return name in self.globals

    def resolve(self, name: str, scope: str = "") -> Symbol | None:
        if scope and scope in self.locals and name in self.locals[scope]:
            return self.locals[scope][name]
        return self.globals.get(name)


def build_symbol_table(tree: ast.AST, path: str) -> SymbolTable:
    st = SymbolTable(path=path)

    def add_global(name: str, kind: str, lineno: int, qual: str = "") -> None:
        if name and name not in st.globals:
            st.globals[name] = Symbol(name=name, kind=kind, lineno=lineno, qualname=qual or name)

    def add_local(scope: str, name: str, kind: str, lineno: int) -> None:
        st.locals.setdefault(scope, {})
        if name and name not in st.locals[scope]:
            st.locals[scope][name] = Symbol(name=name, kind=kind, lineno=lineno, qualname=f"{scope}.{name}")

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            add_global(node.name, "function", node.lineno)
            scope = node.name
            for a in node.args.args:
                add_local(scope, a.arg, "param", getattr(a, "lineno", node.lineno) or node.lineno)
        elif isinstance(node, ast.AsyncFunctionDef):
            add_global(node.name, "async_function", node.lineno)
            scope = node.name
            for a in node.args.args:
                add_local(scope, a.arg, "param", getattr(a, "lineno", node.lineno) or node.lineno)
        elif isinstance(node, ast.ClassDef):
            add_global(node.name, "class", node.lineno)
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    kind = "async_function" if isinstance(item, ast.AsyncFunctionDef) else "function"
                    add_global(item.name, kind, item.lineno, qual=f"{node.name}.{item.name}")
                    scope = f"{node.name}.{item.name}"
                    for a in item.args.args:
                        add_local(scope, a.arg, "param", getattr(a, "lineno", item.lineno) or item.lineno)
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    add_global(t.id, "assign", node.lineno)
        elif isinstance(node, ast.Import):
            for a in node.names:
                add_global(a.asname or a.name.split(".")[0], "import", node.lineno)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                add_global(a.asname or a.name, "import", node.lineno)

    return st
