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
    command_bindings: list[tuple[str, str]] = field(default_factory=list)

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
            "command_bindings": list(self.command_bindings),
        }


_CMD_BIND_RE = re.compile(
    r"CommandHandler\(\s*['\"]([a-zA-Z][a-zA-Z0-9_]*)['\"]\s*,\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)"
)
_ASYNC_DEF_RE = re.compile(r"async def ([a-zA-Z_][a-zA-Z0-9_]*)\s*\(")


def _handler_body(src: str, name: str) -> str:
    m = re.search(rf"async def {re.escape(name)}\s*\(", src)
    if not m:
        return ""
    rest = src[m.end() :]
    end_m = re.search(r"\nasync def |\n_CMD_HANDLERS|\ndef main\b", rest)
    return rest[: end_m.start()] if end_m else rest[:2500]


def _looks_stub(body: str) -> bool:
    if not body.strip():
        return True
    real_markers = (
        "reply_text",
        "reply_html",
        "reply_markdown",
        "answer_callback",
        "market_svc",
        "extras_svc",
        "security_svc",
        "list_records",
        "create_record",
        "update_record",
        "run_tool",
        "FLOWS",
        "_start_flow",
        "context.bot",
        "PreCheckoutQuery",
        "SuccessfulPayment",
        "await ",
    )
    return not any(k in body for k in real_markers)


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
    combined = main_t + "\n" + h_t

    bindings = _CMD_BIND_RE.findall(combined)
    rep.command_bindings = [(c, h) for c, h in bindings]
    rep.commands_registered = [c for c, _ in bindings]
    rep.handler_fns = _ASYNC_DEF_RE.findall(h_t)
    handler_set = set(rep.handler_fns)
    # also accept handlers defined in main.py
    handler_set.update(_ASYNC_DEF_RE.findall(main_t))

    rep.has_message_handler = (
        "async def message_handler" in combined
        or "MessageHandler(" in main_t
    )
    rep.has_msgs_init = bool(re.search(r"msgs\s*=\s*\[\]", h_t))

    if not rep.has_message_handler and not rep.commands_registered:
        rep.ok = False
        rep.errors.append("message_handler_missing")

    # Stub detection on bound handlers only
    seen_handlers: set[str] = set()
    for cmd, hname in bindings:
        if hname in seen_handlers:
            continue
        seen_handlers.add(hname)
        body = _handler_body(h_t, hname) or _handler_body(main_t, hname)
        if hname not in handler_set:
            rep.ok = False
            rep.errors.append(f"missing_handler:{cmd}")
            continue
        if _looks_stub(body) and hname not in ("start_handler", "help_handler"):
            rep.stub_handlers.append(hname)
            rep.warnings.append(f"stub_handler:{hname}")

    # Every CommandHandler must resolve to a defined async function
    for cmd, hname in bindings:
        if hname not in handler_set:
            if f"missing_handler:{cmd}" not in rep.errors:
                rep.ok = False
                rep.errors.append(f"missing_handler:{cmd}")

    return rep


__all__ = ["GenVerifyReport", "verify_generated_project"]
