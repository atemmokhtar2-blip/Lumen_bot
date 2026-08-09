"""Post-generation verification — structural + static, no domain templates."""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class GenVerifyReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    commands_registered: list[str] = field(default_factory=list)
    handler_fns: list[str] = field(default_factory=list)
    has_message_handler: bool = False
    has_msgs_init: bool = False
    stub_handlers: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "commands_registered": list(self.commands_registered),
            "handler_fns": list(self.handler_fns),
            "has_message_handler": self.has_message_handler,
            "has_msgs_init": self.has_msgs_init,
            "stub_handlers": list(self.stub_handlers),
        }


def verify_generated_project(project_path: str | Path) -> GenVerifyReport:
    root = Path(project_path)
    rep = GenVerifyReport(ok=True)
    if not root.is_dir():
        rep.ok = False
        rep.errors.append("project_missing")
        return rep

    main = root / "main.py"
    handlers = root / "app" / "handlers.py"
    if not main.is_file():
        rep.ok = False
        rep.errors.append("main_py_missing")
    if not handlers.is_file():
        rep.ok = False
        rep.errors.append("handlers_py_missing")
        return rep

    for py in root.rglob("*.py"):
        if any(x in py.parts for x in (".venv", "venv", "__pycache__")):
            continue
        try:
            ast.parse(py.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as e:
            rep.ok = False
            rep.errors.append(f"syntax:{py.relative_to(root)}:{e.lineno}")

    main_t = main.read_text(encoding="utf-8", errors="ignore") if main.is_file() else ""
    h_t = handlers.read_text(encoding="utf-8", errors="ignore")

    rep.commands_registered = re.findall(
        r"CommandHandler\(\s*['\"]([a-zA-Z][a-zA-Z0-9_]*)['\"]",
        main_t,
    )
    rep.handler_fns = re.findall(r"async def ([a-zA-Z_][a-zA-Z0-9_]*)\(", h_t)
    rep.has_message_handler = "async def message_handler" in h_t
    rep.has_msgs_init = bool(re.search(r"msgs\s*=\s*\[\]", h_t))

    if not rep.has_message_handler:
        rep.ok = False
        rep.errors.append("message_handler_missing")
    if not rep.has_msgs_init and "FLOWS" in h_t:
        if re.search(r"FLOWS[^\n]*=\s*\{[^}]+\[", h_t, re.S):
            rep.ok = False
            rep.errors.append("msgs_init_missing_with_flows")

    for m in re.finditer(r"async def ([a-zA-Z_][a-zA-Z0-9_]*)_handler\(", h_t):
        name = m.group(1)
        if name in ("start", "help", "message", "callback"):
            continue
        rest = h_t[m.end() :]
        end_m = re.search(r"\nasync def |\n_CMD_HANDLERS", rest)
        body = rest[: end_m.start()] if end_m else rest[:2500]
        real = any(
            k in body
            for k in (
                "_start_flow",
                "list_records",
                "create_record",
                "update_record",
                "run_tool",
                "FLOWS.get",
            )
        )
        if not real:
            rep.stub_handlers.append(name)
            rep.warnings.append(f"stub_handler:{name}")

    for cmd in rep.commands_registered:
        if f"async def {cmd}_handler" not in h_t:
            rep.ok = False
            rep.errors.append(f"missing_handler:{cmd}")

    return rep


__all__ = ["GenVerifyReport", "verify_generated_project"]
