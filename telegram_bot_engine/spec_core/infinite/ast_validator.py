"""Strict AST/DAG validator for DynamicBotSpec — schema-level self-correction."""
from __future__ import annotations

from typing import Any

from .atomic_primitives import MAX_DAG_DEPTH
from .infinite_schema import DynamicBotSpec


class SpecValidationError(ValueError):
    """Raised with machine-readable codes for LLM repair loops."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}:{detail}" if detail else code)


def _detect_cycles(nodes: list) -> list[str]:
    """Return list of node ids involved in cycles (DFS)."""
    graph = {n.id: n.next_node_id for n in nodes}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n.id: WHITE for n in nodes}
    cycles: list[str] = []

    def dfs(u: str) -> None:
        color[u] = GRAY
        v = graph.get(u)
        if v:
            if color.get(v) == GRAY:
                cycles.append(u)
            elif color.get(v) == WHITE:
                dfs(v)
        color[u] = BLACK

    for nid in graph:
        if color[nid] == WHITE:
            dfs(nid)
    return cycles


def _max_chain_depth(nodes: list) -> int:
    graph = {n.id: n.next_node_id for n in nodes}
    memo: dict[str, int] = {}

    def depth(u: str, stack: set[str]) -> int:
        if u in stack:
            return 0
        if u in memo:
            return memo[u]
        nxt = graph.get(u)
        if not nxt or nxt not in graph:
            memo[u] = 1
            return 1
        stack.add(u)
        d = 1 + depth(nxt, stack)
        stack.discard(u)
        memo[u] = d
        return d

    return max((depth(n.id, set()) for n in nodes), default=0)


def validate_dynamic_spec(spec: DynamicBotSpec | dict[str, Any]) -> DynamicBotSpec:
    """Parse + enforce deterministic safety. Raises SpecValidationError."""
    if isinstance(spec, dict):
        try:
            spec = DynamicBotSpec.model_validate(spec)
        except Exception as exc:
            raise SpecValidationError("schema_invalid", str(exc)[:400]) from exc

    cycles = _detect_cycles(spec.nodes)
    if cycles:
        raise SpecValidationError("infinite_loop_detected", ",".join(cycles[:8]))

    depth = _max_chain_depth(spec.nodes)
    if depth > MAX_DAG_DEPTH:
        raise SpecValidationError("dag_depth_exceeded", f"{depth}>{MAX_DAG_DEPTH}")

    # Every node must have a trigger (schema already requires it)
    # Prefer at least one entry trigger
    entry_types = {"on_start", "on_command", "on_message", "on_callback"}
    if not any(n.trigger.type in entry_types for n in spec.nodes):
        raise SpecValidationError("no_entry_trigger", "need_on_start_or_command_or_message")

    # call_external_api must declare url host (checked further at runtime proxy)
    for n in spec.nodes:
        for act in n.actions:
            if act.type == "call_external_api":
                url = str((act.config or {}).get("url") or "")
                if not url.startswith("https://"):
                    raise SpecValidationError(
                        "api_url_must_be_https",
                        f"node={n.id}",
                    )
                low = url.lower()
                if any(
                    x in low
                    for x in (
                        "localhost",
                        "127.0.0.1",
                        "0.0.0.0",
                        "169.254.",
                        "10.",
                        "192.168.",
                        "metadata.google",
                        "169.254.169.254",
                    )
                ):
                    raise SpecValidationError("api_url_ssrf_blocked", f"node={n.id}")

    return spec


def validation_errors_for_llm(exc: Exception) -> dict[str, Any]:
    """Structured error payload to feed back into LLM self-correction."""
    if isinstance(exc, SpecValidationError):
        return {"ok": False, "code": exc.code, "detail": exc.detail}
    return {"ok": False, "code": "schema_invalid", "detail": str(exc)[:400]}
