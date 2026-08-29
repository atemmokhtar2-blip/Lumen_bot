"""Control-flow graph construction."""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Iterable

from . import models as M
from .models import (
    BasicBlock,
    CFG,
    NameEvent,
    Nullability,
    FunctionFlow,
    ModuleFlow,
    _assign_targets,
    _is_none_constant,
    _terminates,
    _call_label,
    _load_builtins,
)

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


