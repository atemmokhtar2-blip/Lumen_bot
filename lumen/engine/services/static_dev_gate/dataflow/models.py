"""CFG models and AST helper utilities for dataflow analysis."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

# ---------------------------------------------------------------------------
# Constants — derived from language semantics, not templates
# ---------------------------------------------------------------------------

_TAINT_SOURCE_ATTRS = {
    ("message", "text"),
    ("message", "caption"),
    ("query", "data"),
    ("update", "text"),
    # common PTB patterns
    ("context", "args"),
    ("update", "message"),
    ("message", "from_user"),
}
_TAINT_SOURCE_NAMES = {
    "user_input", "text", "raw", "payload", "data", "cmd", "query_text", "blob",
}
# attribute names that are user-controlled when loaded from any object
_TAINT_ATTR_NAMES = {
    "text", "caption", "data", "args", "query", "username", "full_name",
}


def _attr_chain(node: ast.AST) -> list[str]:
    """update.message.text → ['update', 'message', 'text']."""
    chain: list[str] = []
    cur: ast.AST = node
    while isinstance(cur, ast.Attribute):
        chain.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        chain.append(cur.id)
        chain.reverse()
        return chain
    return []


def _chain_is_taint_source(chain: list[str]) -> bool:
    if not chain:
        return False
    if chain[0] in _TAINT_SOURCE_NAMES:
        return True
    if chain[0] in ("update", "message", "query", "context", "callback_query"):
        # any attr under telegram user-facing objects is treated as taint source
        return True
    for i in range(len(chain) - 1):
        if (chain[i], chain[i + 1]) in _TAINT_SOURCE_ATTRS:
            return True
    if chain[-1] in _TAINT_ATTR_NAMES:
        return True
    return False


def _expr_carries_taint(node: ast.AST, tainted: set[str]) -> bool:
    """Whether an expression transitively carries user-controlled data."""
    for n in ast.walk(node):
        if isinstance(n, ast.Name) and (n.id in tainted or n.id in _TAINT_SOURCE_NAMES):
            return True
        if isinstance(n, ast.Attribute):
            chain = _attr_chain(n)
            if _chain_is_taint_source(chain):
                return True
            if chain and chain[0] in tainted:
                return True
        if isinstance(n, ast.JoinedStr):
            for v in n.values:
                if isinstance(v, ast.FormattedValue) and _expr_carries_taint(v.value, tainted):
                    return True
    return False

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
    "subprocess.check_output",
    "subprocess.check_call",
    "pickle.loads",
    "pickle.load",
    # SQL injection surfaces
    "execute",
    "executemany",
    "executescript",
    "cursor.execute",
    "Cursor.execute",
    "connection.execute",
    "Connection.execute",
}

# Attribute names that are SQL sinks when called on any object
_SQL_SINK_ATTRS = {"execute", "executemany", "executescript"}

# Resource factories: call label → resource kind
_RESOURCE_OPENERS = {
    "open": "file",
    "io.open": "file",
    "Path.open": "file",
    "socket.socket": "socket",
    "socket.create_connection": "socket",
    "sqlite3.connect": "db",
    "psycopg2.connect": "db",
    "pymysql.connect": "db",
    "redis.Redis": "redis",
    "redis.from_url": "redis",
    "aiohttp.ClientSession": "http_session",
    "httpx.Client": "http_session",
    "httpx.AsyncClient": "http_session",
    "requests.Session": "http_session",
}

_RESOURCE_CLOSERS = {
    "close",
    "aclose",
    "shutdown",
    "disconnect",
    "quit",
}


class Nullability(str, Enum):
    """Conservative nullability lattice for a name at a program point."""

    NOT_NONE = "not_none"
    MAYBE_NONE = "maybe_none"
    DEFINITE_NONE = "definite_none"
    UNKNOWN = "unknown"

    def join(self, other: "Nullability") -> "Nullability":
        """Lattice join (merge of two branches / expression sides)."""
        if self == other:
            return self
        # UNKNOWN never collapses into DEFINITE_NONE — becomes MAYBE_NONE
        if Nullability.UNKNOWN in (self, other):
            return Nullability.MAYBE_NONE
        if {self, other} == {Nullability.DEFINITE_NONE, Nullability.NOT_NONE}:
            return Nullability.MAYBE_NONE
        if Nullability.MAYBE_NONE in (self, other):
            return Nullability.MAYBE_NONE
        return Nullability.MAYBE_NONE


# ---------------------------------------------------------------------------
# Core models — shared substrate for later engines
# ---------------------------------------------------------------------------


@dataclass
class NameEvent:
    name: str
    lineno: int
    kind: str  # def | use
    context: str = ""  # function qualname


@dataclass
class BasicBlock:
    """Single-entry linear sequence of statements (CFG node)."""

    id: int
    stmts: list[ast.stmt] = field(default_factory=list)
    successors: list[int] = field(default_factory=list)
    predecessors: list[int] = field(default_factory=list)
    # True if control never enters this block (computed post-CFG)
    unreachable: bool = False
    start_lineno: int = 0
    end_lineno: int = 0


@dataclass
class CFG:
    """Control-flow graph for one function body."""

    blocks: dict[int, BasicBlock] = field(default_factory=dict)
    entry: int = 0
    exits: list[int] = field(default_factory=list)

    def add_edge(self, src: int, dst: int) -> None:
        if dst not in self.blocks[src].successors:
            self.blocks[src].successors.append(dst)
        if src not in self.blocks[dst].predecessors:
            self.blocks[dst].predecessors.append(src)


@dataclass
class MaybeNoneUse:
    """A load of a name that may be None at that point."""

    name: str
    lineno: int
    nullability: Nullability
    context: str = ""


@dataclass
class ResourceEvent:
    """Acquisition or release of an external resource."""

    kind: str  # file | socket | db | redis | http_session | other
    name: str  # bound variable, or "" if anonymous
    lineno: int
    action: str  # open | close
    via_with: bool = False
    call_label: str = ""


@dataclass
class FunctionFlow:
    """
    Full per-function analysis result.

    Backward-compatible fields kept for existing rules:
      params, events, use_before_def, unused_locals, dangerous_sinks,
      tainted_to_sink, has_await, is_async, unreachable_lines
    """

    qualname: str
    file: str
    lineno: int
    params: set[str] = field(default_factory=set)
    events: list[NameEvent] = field(default_factory=list)
    use_before_def: list[tuple[str, int]] = field(default_factory=list)
    unused_locals: set[str] = field(default_factory=set)
    dangerous_sinks: list[tuple[str, int, str]] = field(default_factory=list)
    tainted_to_sink: list[tuple[str, str, int]] = field(default_factory=list)
    has_await: bool = False
    is_async: bool = False
    unreachable_lines: list[int] = field(default_factory=list)
    # --- Phase extensions ---
    cfg: CFG | None = None
    maybe_none_uses: list[MaybeNoneUse] = field(default_factory=list)
    resource_events: list[ResourceEvent] = field(default_factory=list)
    # names acquired but never closed and not under `with`
    resource_leaks: list[tuple[str, str, int]] = field(default_factory=list)
    # name, kind, lineno of acquisition


@dataclass
class ModuleFlow:
    path: str
    functions: list[FunctionFlow] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _is_none_constant(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value is None


def _terminates(stmt: ast.stmt) -> bool:
    """Statement that ends the current basic block's fall-through."""
    return isinstance(
        stmt,
        (
            ast.Return,
            ast.Raise,
            ast.Break,
            ast.Continue,
            ast.If,
            ast.For,
            ast.While,
            ast.With,
            ast.AsyncWith,
            ast.Try,
            ast.Match,
        ),
    )


def _load_builtins() -> set[str]:
    names: set[str] = set()
    b = __builtins__
    if isinstance(b, dict):
        names |= set(b.keys())
    else:
        names |= set(dir(b))
    names |= {
        "print", "len", "range", "list", "dict", "set", "tuple", "str", "int",
        "float", "bool", "type", "isinstance", "issubclass", "getattr", "setattr",
        "hasattr", "enumerate", "zip", "map", "filter", "sorted", "sum", "min",
        "max", "open", "eval", "exec", "compile", "__import__", "input", "iter",
        "next", "id", "Exception", "ValueError", "TypeError", "KeyError",
        "AttributeError", "RuntimeError", "StopIteration", "True", "False",
        "None", "object", "super", "property", "classmethod", "staticmethod",
        "BaseException", "asyncio", "contextlib",
    }
    return names


_BUILTINS = _load_builtins()


# ---------------------------------------------------------------------------
# Phase 1 — CFG builder (statement-level basic blocks)
# ---------------------------------------------------------------------------


