"""
Control & Data Flow Analysis on Python AST (stdlib `ast` only).

Foundation phases (extensible — no fixed templates):
  Phase 1 — CFG: basic blocks + control edges from AST statements
  Phase 2 — Reachability: unreachable code after return/raise/break/continue
  Phase 3 — Definite assignment + use-before-def (branch-conservative)
  Phase 4 — Maybe-None: track names that may be None at use sites
  Phase 5 — Resource lifecycle: open/connect without close / without `with`
  Phase 6 — Taint: user-controlled values reaching dangerous sinks

Designed so Symbolic Execution / AST Pattern Matching / DbC can plug into
the same FunctionFlow / CFG structures in later stages without rewrite.
"""

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


class _CFGBuilder:
    """
    Build a CFG from a list of statements.

    Strategy: sequential statements share a block until a terminator
    (return/raise/break/continue) or a structured control node
    (if/for/while/with/try). Structured nodes become their own blocks
    with edges to body / orelse / next.
    """

    def __init__(self) -> None:
        self.cfg = CFG()
        self._next_id = 0

    def _new_block(self) -> BasicBlock:
        bid = self._next_id
        self._next_id += 1
        b = BasicBlock(id=bid)
        self.cfg.blocks[bid] = b
        return b

    def build(self, body: list[ast.stmt]) -> CFG:
        entry = self._new_block()
        self.cfg.entry = entry.id
        exit_ids = self._fill(entry, body)
        self.cfg.exits = exit_ids
        self._mark_reachable()
        return self.cfg

    def _fill(self, block: BasicBlock, stmts: list[ast.stmt]) -> list[int]:
        """Fill `block` with stmts; return list of exit block ids (fall-through)."""
        i = 0
        while i < len(stmts):
            stmt = stmts[i]
            if not block.stmts:
                block.start_lineno = getattr(stmt, "lineno", 0) or 0
            block.stmts.append(stmt)
            block.end_lineno = getattr(stmt, "lineno", 0) or block.end_lineno

            if isinstance(stmt, (ast.Return, ast.Raise)):
                # no fall-through
                return []

            if isinstance(stmt, (ast.Break, ast.Continue)):
                return []

            if isinstance(stmt, ast.If):
                then_b = self._new_block()
                else_b = self._new_block()
                self.cfg.add_edge(block.id, then_b.id)
                self.cfg.add_edge(block.id, else_b.id)
                then_exits = self._fill(then_b, list(stmt.body))
                else_exits = self._fill(else_b, list(stmt.orelse))
                join_exits = then_exits + else_exits
                rest = stmts[i + 1 :]
                if not rest:
                    return join_exits
                if not join_exits:
                    # both branches terminated — rest is unreachable
                    dead = self._new_block()
                    dead.unreachable = True
                    self._fill(dead, rest)
                    return []
                cont = self._new_block()
                for eid in join_exits:
                    self.cfg.add_edge(eid, cont.id)
                return self._fill(cont, rest)

            if isinstance(stmt, (ast.For, ast.While)):
                body_b = self._new_block()
                else_b = self._new_block()
                self.cfg.add_edge(block.id, body_b.id)
                self.cfg.add_edge(block.id, else_b.id)
                body_exits = self._fill(body_b, list(stmt.body))
                # loop-back
                for eid in body_exits:
                    self.cfg.add_edge(eid, body_b.id)
                    self.cfg.add_edge(eid, else_b.id)
                else_exits = self._fill(else_b, list(stmt.orelse))
                rest = stmts[i + 1 :]
                cont_exits = body_exits + else_exits
                if not rest:
                    return cont_exits if cont_exits else [else_b.id]
                cont = self._new_block()
                sources = cont_exits if cont_exits else [else_b.id]
                for eid in sources:
                    self.cfg.add_edge(eid, cont.id)
                # also edge from header for zero-iteration path
                self.cfg.add_edge(block.id, cont.id)
                return self._fill(cont, rest)

            if isinstance(stmt, (ast.With, ast.AsyncWith)):
                body_b = self._new_block()
                self.cfg.add_edge(block.id, body_b.id)
                body_exits = self._fill(body_b, list(stmt.body))
                rest = stmts[i + 1 :]
                if not rest:
                    return body_exits if body_exits else []
                if not body_exits:
                    dead = self._new_block()
                    dead.unreachable = True
                    self._fill(dead, rest)
                    return []
                cont = self._new_block()
                for eid in body_exits:
                    self.cfg.add_edge(eid, cont.id)
                return self._fill(cont, rest)

            if isinstance(stmt, ast.Try):
                body_b = self._new_block()
                self.cfg.add_edge(block.id, body_b.id)
                body_exits = self._fill(body_b, list(stmt.body))
                handler_exits: list[int] = []
                for h in stmt.handlers:
                    hb = self._new_block()
                    self.cfg.add_edge(block.id, hb.id)
                    handler_exits.extend(self._fill(hb, list(h.body)))
                else_exits: list[int] = []
                if stmt.orelse:
                    eb = self._new_block()
                    for eid in body_exits:
                        self.cfg.add_edge(eid, eb.id)
                    else_exits = self._fill(eb, list(stmt.orelse))
                final_exits: list[int] = []
                if stmt.finalbody:
                    fb = self._new_block()
                    for eid in body_exits + handler_exits + else_exits:
                        self.cfg.add_edge(eid, fb.id)
                    final_exits = self._fill(fb, list(stmt.finalbody))
                    join = final_exits
                else:
                    join = body_exits + handler_exits + else_exits
                rest = stmts[i + 1 :]
                if not rest:
                    return join
                if not join:
                    dead = self._new_block()
                    dead.unreachable = True
                    self._fill(dead, rest)
                    return []
                cont = self._new_block()
                for eid in join:
                    self.cfg.add_edge(eid, cont.id)
                return self._fill(cont, rest)

            # ordinary statement — stay in same block
            i += 1

        return [block.id]

    def _mark_reachable(self) -> None:
        """BFS from entry; anything not reached is unreachable."""
        seen: set[int] = set()
        stack = [self.cfg.entry]
        while stack:
            bid = stack.pop()
            if bid in seen:
                continue
            seen.add(bid)
            b = self.cfg.blocks[bid]
            if b.unreachable:
                continue
            for s in b.successors:
                stack.append(s)
        for bid, b in self.cfg.blocks.items():
            if bid not in seen:
                b.unreachable = True


# ---------------------------------------------------------------------------
# Phase 2–6 — Flow visitor (assignment, nullability, resources, taint)
# ---------------------------------------------------------------------------


class _FlowVisitor(ast.NodeVisitor):
    """
    Linear + branch-conservative analysis inside one function.

    Tracks:
      - definite assignment (use-before-def)
      - nullability lattice per name
      - resource open/close
      - taint propagation to sinks
      - statements after unconditional exit (unreachable lines)
    """

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
        self._returned = False  # sequential dead-code flag
        self._null: dict[str, Nullability] = {p: Nullability.UNKNOWN for p in params}
        self.maybe_none_uses: list[MaybeNoneUse] = []
        self.resource_events: list[ResourceEvent] = []
        # name → (kind, lineno, via_with)
        self._open_resources: dict[str, tuple[str, int, bool]] = {}

    # -- helpers -------------------------------------------------------------

    def _use(self, name: str, lineno: int) -> None:
        if name in ("True", "False", "None"):
            return
        self.events.append(NameEvent(name, lineno, "use", self.qualname))
        self._used.add(name)
        if name not in self.defined and not name.isupper():
            if name in _BUILTINS:
                return
            self.use_before_def.append((name, lineno))
        # nullability check at use
        nstate = self._null.get(name, Nullability.UNKNOWN)
        if nstate in (Nullability.MAYBE_NONE, Nullability.DEFINITE_NONE):
            self.maybe_none_uses.append(
                MaybeNoneUse(name, lineno, nstate, self.qualname)
            )

    def _def(self, name: str, lineno: int, null: Nullability = Nullability.UNKNOWN) -> None:
        self.events.append(NameEvent(name, lineno, "def", self.qualname))
        self.defined.add(name)
        self._assigned_locals.add(name)
        self._null[name] = null

    def _infer_null(self, value: ast.AST) -> Nullability:
        if _is_none_constant(value):
            return Nullability.DEFINITE_NONE
        if isinstance(value, ast.Constant):
            return Nullability.NOT_NONE
        if isinstance(value, ast.Name):
            return self._null.get(value.id, Nullability.UNKNOWN)
        if isinstance(value, ast.IfExp):
            a = self._infer_null(value.body)
            b = self._infer_null(value.orelse)
            return a.join(b)
        if isinstance(value, ast.BoolOp) and isinstance(value.op, ast.Or):
            # x or default  → if x is maybe_none, result may still be none
            states = [self._infer_null(v) for v in value.values]
            out = states[0]
            for s in states[1:]:
                out = out.join(s)
            return out
        if isinstance(value, ast.Call):
            label = _call_label(value.func)
            # dict.get / .get without default → MAYBE_NONE
            if isinstance(value.func, ast.Attribute) and value.func.attr == "get":
                has_default = len(value.args) >= 2 or any(
                    kw.arg == "default" for kw in value.keywords
                )
                if has_default:
                    # type of default may be none-ish; conservative maybe
                    if len(value.args) >= 2:
                        return self._infer_null(value.args[1]).join(Nullability.MAYBE_NONE)
                    return Nullability.MAYBE_NONE
                return Nullability.MAYBE_NONE
            # common factories that never return None
            if label in ("dict", "list", "set", "tuple", "str", "int", "float", "bool"):
                return Nullability.NOT_NONE
            if label in _RESOURCE_OPENERS or label == "open":
                return Nullability.NOT_NONE
            # open(...).read() still NOT_NONE for the string, but resource handled elsewhere
            return Nullability.UNKNOWN
        if isinstance(value, (ast.List, ast.Dict, ast.Set, ast.Tuple, ast.JoinedStr)):
            return Nullability.NOT_NONE
        if isinstance(value, ast.Subscript):
            base = self._infer_null(value.value)
            if base in (Nullability.MAYBE_NONE, Nullability.DEFINITE_NONE):
                return base
            return Nullability.UNKNOWN
        return Nullability.UNKNOWN

    def _note_resource_open(
        self,
        label: str,
        lineno: int,
        bound_names: list[str],
        via_with: bool,
    ) -> None:
        kind = _RESOURCE_OPENERS.get(label, "")
        if not kind and label == "open":
            kind = "file"
        if not kind:
            # partial match (e.g. path.open)
            for k, v in _RESOURCE_OPENERS.items():
                if label.endswith("." + k.split(".")[-1]) or label == k:
                    kind = v
                    break
        if not kind:
            return
        if bound_names:
            for n in bound_names:
                self.resource_events.append(
                    ResourceEvent(kind=kind, name=n, lineno=lineno, action="open",
                                  via_with=via_with, call_label=label)
                )
                self._open_resources[n] = (kind, lineno, via_with)
        else:
            self.resource_events.append(
                ResourceEvent(kind=kind, name="", lineno=lineno, action="open",
                              via_with=via_with, call_label=label)
            )

    def _note_resource_close(self, name: str, lineno: int) -> None:
        if name in self._open_resources:
            kind, _, _ = self._open_resources.pop(name)
            self.resource_events.append(
                ResourceEvent(kind=kind, name=name, lineno=lineno, action="close")
            )

    # -- visitors ------------------------------------------------------------

    def visit_Name(self, node: ast.Name) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        if isinstance(node.ctx, ast.Load):
            self._use(node.id, node.lineno)
        elif isinstance(node.ctx, (ast.Store, ast.Param)):
            self._def(node.id, node.lineno)

    def visit_arg(self, node: ast.arg) -> None:
        self._def(node.arg, getattr(node, "lineno", 0) or 0)

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        self.visit(node.value)
        null = self._infer_null(node.value)
        tainted_value = _expr_carries_taint(node.value, self.tainted)
        # resource open via assignment: f = open(...) OR data = open(...).read()
        bound: list[str] = []
        for t in node.targets:
            bound.extend(_assign_targets(t))
        self._detect_resource_in_expr(node.value, node.lineno, bound)
        for t in node.targets:
            for n in _assign_targets(t):
                self._def(n, node.lineno, null)
                if tainted_value:
                    self.tainted.add(n)
            # targets are Store — already handled; do not re-visit
            # (re-visit would overwrite nullability with UNKNOWN)

    def _detect_resource_in_expr(
        self, value: ast.AST, lineno: int, bound: list[str]
    ) -> None:
        """Flag open()/connect() even when chained: open(x).read()."""
        if isinstance(value, ast.Call):
            # method chain first: open(path).read() → resource is the inner open (unbound)
            if isinstance(value.func, ast.Attribute):
                self._detect_resource_in_expr(value.func.value, lineno, [])
            label = _call_label(value.func)
            is_opener = (
                label in _RESOURCE_OPENERS
                or label == "open"
                or label.endswith(".open")
                or (isinstance(value.func, ast.Name) and value.func.id == "open")
            )
            if is_opener:
                self._note_resource_open(label or "open", lineno, bound, False)
            for a in value.args:
                if isinstance(a, (ast.Call, ast.Attribute)):
                    self._detect_resource_in_expr(a, lineno, [])
        elif isinstance(value, ast.Attribute):
            self._detect_resource_in_expr(value.value, lineno, bound)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        null = Nullability.UNKNOWN
        if node.value is not None:
            self.visit(node.value)
            null = self._infer_null(node.value)
            bound = _assign_targets(node.target)
            self._detect_resource_in_expr(node.value, node.lineno, bound)
            if _expr_carries_taint(node.value, self.tainted):
                for n in bound:
                    self.tainted.add(n)
        for n in _assign_targets(node.target):
            self._def(n, node.lineno, null)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        self.visit(node.value)
        if isinstance(node.target, ast.Name):
            self._use(node.target.id, node.lineno)
            prev = self._null.get(node.target.id, Nullability.UNKNOWN)
            self._def(node.target.id, node.lineno, prev)
        else:
            self.visit(node.target)

    def visit_For(self, node: ast.For) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        self.visit(node.iter)
        for n in _assign_targets(node.target):
            self._def(n, node.lineno, Nullability.UNKNOWN)
        before = set(self.defined)
        before_null = dict(self._null)
        for stmt in node.body:
            self.visit(stmt)
        after_body_null = dict(self._null)
        self.defined = set(before)
        self._null = dict(before_null)
        for stmt in node.orelse:
            self.visit(stmt)
        after_else_null = dict(self._null)
        self.defined = before | (self.defined & set(before))  # conservative
        # merge nullability
        all_names = set(after_body_null) | set(after_else_null) | set(before_null)
        for name in all_names:
            a = after_body_null.get(name, before_null.get(name, Nullability.UNKNOWN))
            b = after_else_null.get(name, before_null.get(name, Nullability.UNKNOWN))
            self._null[name] = a.join(b)

    def visit_With(self, node: ast.With) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        for item in node.items:
            self.visit(item.context_expr)
            bound: list[str] = []
            if item.optional_vars is not None:
                bound = _assign_targets(item.optional_vars)
                for n in bound:
                    self._def(n, node.lineno, Nullability.NOT_NONE)
            if isinstance(item.context_expr, ast.Call):
                self._note_resource_open(
                    _call_label(item.context_expr.func),
                    node.lineno,
                    bound,
                    via_with=True,
                )
        for stmt in node.body:
            self.visit(stmt)
        # resources opened via `with` are considered closed on exit
        for n in list(self._open_resources):
            kind, ln, via = self._open_resources[n]
            if via:
                self._note_resource_close(n, node.lineno)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        # same treatment as With
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        for item in node.items:
            self.visit(item.context_expr)
            bound: list[str] = []
            if item.optional_vars is not None:
                bound = _assign_targets(item.optional_vars)
                for n in bound:
                    self._def(n, node.lineno, Nullability.NOT_NONE)
            if isinstance(item.context_expr, ast.Call):
                self._note_resource_open(
                    _call_label(item.context_expr.func),
                    node.lineno,
                    bound,
                    via_with=True,
                )
        for stmt in node.body:
            self.visit(stmt)
        for n in list(self._open_resources):
            kind, ln, via = self._open_resources[n]
            if via:
                self._note_resource_close(n, node.lineno)

    def visit_If(self, node: ast.If) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        self.visit(node.test)
        # narrow nullability on `if x is None` / `if x is not None`
        narrowed_then: dict[str, Nullability] = {}
        narrowed_else: dict[str, Nullability] = {}
        if isinstance(node.test, ast.Compare) and len(node.test.ops) == 1:
            left, op, comps = node.test.left, node.test.ops[0], node.test.comparators
            if len(comps) == 1 and _is_none_constant(comps[0]) and isinstance(left, ast.Name):
                if isinstance(op, ast.IsNot):
                    # if x is not None:  then→NOT_NONE  else→DEFINITE_NONE
                    narrowed_then[left.id] = Nullability.NOT_NONE
                    narrowed_else[left.id] = Nullability.DEFINITE_NONE
                elif isinstance(op, ast.Is):
                    # if x is None:  then→DEFINITE_NONE  else→NOT_NONE
                    narrowed_then[left.id] = Nullability.DEFINITE_NONE
                    narrowed_else[left.id] = Nullability.NOT_NONE

        before = set(self.defined)
        before_null = dict(self._null)
        # then
        for k, v in narrowed_then.items():
            self._null[k] = v
        was_returned = self._returned
        for stmt in node.body:
            self.visit(stmt)
        after_then = set(self.defined)
        after_then_null = dict(self._null)
        then_returned = self._returned
        # else
        self.defined = set(before)
        self._null = dict(before_null)
        for k, v in narrowed_else.items():
            self._null[k] = v
        self._returned = was_returned
        for stmt in node.orelse:
            self.visit(stmt)
        after_else = set(self.defined)
        after_else_null = dict(self._null)
        else_returned = self._returned
        # merge
        self.defined = before | (after_then & after_else)
        all_names = set(after_then_null) | set(after_else_null) | set(before_null)
        for name in all_names:
            a = after_then_null.get(name, before_null.get(name, Nullability.UNKNOWN))
            b = after_else_null.get(name, before_null.get(name, Nullability.UNKNOWN))
            self._null[name] = a.join(b)
        # if both branches return, subsequent code is dead
        self._returned = then_returned and else_returned
        # Early-return guard refinement:
        #   if x is None: return   → after if, x is NOT_NONE on continuing path
        #   if x is not None: return → after if, x may still be None
        if then_returned and not else_returned:
            for name, v in narrowed_else.items():
                self._null[name] = v
        elif else_returned and not then_returned:
            for name, v in narrowed_then.items():
                self._null[name] = v

    def visit_While(self, node: ast.While) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        self.visit(node.test)
        before = set(self.defined)
        before_null = dict(self._null)
        for stmt in node.body:
            self.visit(stmt)
        after_body_null = dict(self._null)
        self.defined = set(before)
        self._null = dict(before_null)
        for stmt in node.orelse:
            self.visit(stmt)
        after_else_null = dict(self._null)
        self.defined = before | (self.defined & set(before))
        all_names = set(after_body_null) | set(after_else_null) | set(before_null)
        for name in all_names:
            a = after_body_null.get(name, before_null.get(name, Nullability.UNKNOWN))
            b = after_else_null.get(name, before_null.get(name, Nullability.UNKNOWN))
            self._null[name] = a.join(b)

    def visit_Call(self, node: ast.Call) -> None:
        if self._returned:
            self.unreachable_lines.append(getattr(node, "lineno", 0) or 0)
            return
        label = _call_label(node.func)
        self.visit(node.func)
        for a in node.args:
            self.visit(a)
        for kw in node.keywords:
            if kw.value is not None:
                self.visit(kw.value)

        # close detection: x.close()
        if isinstance(node.func, ast.Attribute) and node.func.attr in _RESOURCE_CLOSERS:
            if isinstance(node.func.value, ast.Name):
                self._note_resource_close(node.func.value.id, node.lineno)

        is_sql = (
            isinstance(node.func, ast.Attribute)
            and node.func.attr in _SQL_SINK_ATTRS
        )
        # exact label or full dotted suffix — never match bare ".run" to subprocess.run
        is_dangerous = label in _DANGEROUS_CALLS or is_sql
        if not is_dangerous:
            for d in _DANGEROUS_CALLS:
                if "." in d and (label == d or label.endswith("." + d)):
                    is_dangerous = True
                    break
                # attribute-only sinks like execute already handled via is_sql / exact
                if "." not in d and label == d:
                    is_dangerous = True
                    break
        if is_dangerous:
            detail = "call"
            risky = False
            for a in node.args:
                if isinstance(a, ast.Name):
                    risky = True
                    detail = f"arg={a.id}"
                elif isinstance(a, ast.Attribute):
                    risky = True
                    detail = f"attr={_call_label(a)}"
                elif isinstance(a, ast.JoinedStr):
                    risky = True
                    detail = "f-string"
                elif isinstance(a, ast.BinOp) and isinstance(a.op, (ast.Mod, ast.Add)):
                    risky = True
                    detail = "format"
                elif isinstance(a, ast.Call):
                    risky = True
                    detail = "call-arg"
            # eval/exec always; OS/subprocess when dynamic; SQL only when user-tainted
            critical = label in ("eval", "exec", "compile", "__import__") or any(
                label == d or label.endswith("." + d.split(".")[-1])
                for d in (
                    "os.system", "os.popen", "subprocess.call", "subprocess.run",
                    "subprocess.Popen", "pickle.loads", "pickle.load",
                )
            )
            if critical and (risky or label in ("eval", "exec", "compile", "__import__")):
                self.dangerous_sinks.append((label or "call", node.lineno, detail))
            elif is_sql:
                tainted_arg = any(_expr_carries_taint(a, self.tainted) for a in node.args)
                if tainted_arg:
                    self.dangerous_sinks.append((label or "execute", node.lineno, "tainted-sql"))
            # taint → sink (names, attrs, f-strings, % format)
            for a in node.args:
                if _expr_carries_taint(a, self.tainted):
                    src = "tainted"
                    if isinstance(a, ast.Name):
                        src = a.id
                    elif isinstance(a, ast.Attribute):
                        ch = _attr_chain(a)
                        src = ".".join(ch) if ch else _call_label(a)
                    elif isinstance(a, ast.JoinedStr):
                        src = "f-string"
                    elif isinstance(a, ast.BinOp):
                        src = "format"
                    self.tainted_to_sink.append((src, label or "call", node.lineno))

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if self._returned:
            return
        self.visit(node.value)
        chain = _attr_chain(node)
        if _chain_is_taint_source(chain) and chain:
            # mark root name as tainted carrier
            self.tainted.add(chain[0])

    def visit_Await(self, node: ast.Await) -> None:
        if self._returned:
            return
        self.has_await = True
        self.visit(node.value)

    def visit_Return(self, node: ast.Return) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        if node.value is not None:
            self.visit(node.value)
        self._returned = True

    def visit_Raise(self, node: ast.Raise) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        if node.exc is not None:
            self.visit(node.exc)
        self._returned = True

    def visit_Break(self, node: ast.Break) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        # inside loop handled by CFG; sequential flag still useful
        self._returned = True

    def visit_Continue(self, node: ast.Continue) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        self._returned = True

    def visit_Import(self, node: ast.Import) -> None:
        """Local / nested imports define names — not use-before-def."""
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        for alias in node.names:
            bound = alias.asname or alias.name.split(".")[0]
            self._def(bound, node.lineno, Nullability.NOT_NONE)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        for alias in node.names:
            if alias.name == "*":
                continue
            bound = alias.asname or alias.name
            self._def(bound, node.lineno, Nullability.NOT_NONE)

    def _visit_comprehension(self, gens: list[ast.comprehension], visit_elt) -> None:
        """
        Comprehension targets (for x in ...) are definitions before the elt
        and filters use them — must not flag use_before_def on `x`.
        """
        for gen in gens:
            self.visit(gen.iter)
            for n in _assign_targets(gen.target):
                self._def(n, getattr(gen.target, "lineno", 0) or 0, Nullability.UNKNOWN)
            for if_test in gen.ifs:
                self.visit(if_test)
        visit_elt()

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node.generators, lambda: self.visit(node.elt))

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node.generators, lambda: self.visit(node.elt))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node.generators, lambda: self.visit(node.elt))

    def visit_DictComp(self, node: ast.DictComp) -> None:
        def _elts() -> None:
            self.visit(node.key)
            self.visit(node.value)
        self._visit_comprehension(node.generators, _elts)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return  # nested: isolated

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return

    def visit_Expr(self, node: ast.Expr) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        self.visit(node.value)

    def visit_Pass(self, node: ast.Pass) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)

    def visit_Delete(self, node: ast.Delete) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        for t in node.targets:
            self.visit(t)

    def visit_Assert(self, node: ast.Assert) -> None:
        if self._returned:
            self.unreachable_lines.append(node.lineno)
            return
        self.visit(node.test)
        if node.msg is not None:
            self.visit(node.msg)

    def visit_Global(self, node: ast.Global) -> None:
        for name in node.names:
            self.defined.add(name)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        for name in node.names:
            self.defined.add(name)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


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
