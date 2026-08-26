"""Tree-sitter Query captures — official Query API for calls/defs."""
from __future__ import annotations

from typing import Any

from tree_sitter import Language, Node, Parser, Query, QueryCursor

import tree_sitter_python as tspython

_LANG = Language(tspython.language())
_PARSER = Parser(_LANG)

_CALL_QUERY = Query(
    _LANG,
    """
(call
  function: [
    (identifier) @callee
    (attribute attribute: (identifier) @callee_attr)
  ]
) @call
""",
)

_DEF_QUERY = Query(
    _LANG,
    """
(function_definition name: (identifier) @func_name) @func
(class_definition name: (identifier) @class_name) @class
""",
)


def extract_calls_and_defs(source: str | bytes, *, path: str = "") -> dict[str, Any]:
    data = source.encode("utf-8") if isinstance(source, str) else source
    tree = _PARSER.parse(data)
    root = tree.root_node

    def text(n: Node) -> str:
        return data[n.start_byte : n.end_byte].decode("utf-8", errors="replace")

    calls: list[dict[str, Any]] = []
    for _pi, caps in QueryCursor(_CALL_QUERY).matches(root):
        callees = list(caps.get("callee") or []) + list(caps.get("callee_attr") or [])
        call_nodes = list(caps.get("call") or [])
        for i, cn in enumerate(callees):
            call_node = call_nodes[i] if i < len(call_nodes) else cn
            calls.append(
                {
                    "name": text(cn),
                    "line": call_node.start_point[0] + 1,
                    "col": call_node.start_point[1],
                    "path": path,
                }
            )

    defs: list[dict[str, Any]] = []
    for _pi, caps in QueryCursor(_DEF_QUERY).matches(root):
        for n in caps.get("func_name") or []:
            defs.append({"kind": "function", "name": text(n), "line": n.start_point[0] + 1, "path": path})
        for n in caps.get("class_name") or []:
            defs.append({"kind": "class", "name": text(n), "line": n.start_point[0] + 1, "path": path})

    return {"path": path, "calls": calls, "defs": defs, "engine": "tree-sitter-query"}


__all__ = ["extract_calls_and_defs"]
