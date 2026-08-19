from __future__ import annotations

from pathlib import Path
from typing import Any

from ..coding_emit_services import (
    _emit_lean_generic_service,
    _emit_lean_named_service,
)
from ..emitters.project_emitters import _emit_market

def _repair_handler_imports(root: Path) -> list[str]:
    """Ensure main.py only imports symbols that handlers.py actually defines.

    Uses the Python AST (not regex) so comments/strings cannot corrupt edits.
    """
    import ast as _ast

    notes: list[str] = []
    main_p = root / "main.py"
    hand_p = root / "app" / "handlers.py"
    if not main_p.is_file() or not hand_p.is_file():
        return notes

    try:
        handlers_src = hand_p.read_text(encoding="utf-8")
        handlers_tree = _ast.parse(handlers_src)
    except SyntaxError as exc:
        notes.append(f"handlers_syntax_error:{exc}")
        return notes

    defined: set[str] = set()
    for node in handlers_tree.body:
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            defined.add(node.name)

    try:
        main_src = main_p.read_text(encoding="utf-8")
        main_tree = _ast.parse(main_src)
    except SyntaxError as exc:
        notes.append(f"main_syntax_error:{exc}")
        return notes

    dropped: list[str] = []
    class _ImportFixer(_ast.NodeTransformer):
        def visit_ImportFrom(self, node: _ast.ImportFrom):  # noqa: N802
            nonlocal dropped
            if node.module == "app.handlers" and node.names:
                kept: list[_ast.alias] = []
                for alias in node.names:
                    name = alias.name
                    if name == "*" or name in defined:
                        kept.append(alias)
                    else:
                        dropped.append(name)
                if not kept and "start_handler" in defined:
                    kept = [_ast.alias(name="start_handler", asname=None)]
                node.names = kept or node.names
            return node

    fixed_tree = _ImportFixer().visit(main_tree)
    _ast.fix_missing_locations(fixed_tree)

    if dropped:
        notes.append(f"dropped_undefined_handler_imports:{','.join(dropped[:20])}")
        # Remove CommandHandler(..., missing_name) registrations via AST
        class _HandlerPruner(_ast.NodeTransformer):
            def visit_Expr(self, node: _ast.Expr):  # noqa: N802
                call = node.value
                if not isinstance(call, _ast.Call):
                    return node
                # app.add_handler(CommandHandler(..., name))
                if not (isinstance(call.func, _ast.Attribute) and call.func.attr == "add_handler"):
                    return node
                if not call.args:
                    return node
                inner = call.args[0]
                if not isinstance(inner, _ast.Call):
                    return node
                func = inner.func
                is_cmd = (
                    (isinstance(func, _ast.Name) and func.id == "CommandHandler")
                    or (isinstance(func, _ast.Attribute) and func.attr == "CommandHandler")
                )
                if not is_cmd:
                    return node
                # last positional or handler= kw often is the callback name
                cb = None
                if len(inner.args) >= 2 and isinstance(inner.args[-1], _ast.Name):
                    cb = inner.args[-1].id
                for kw in inner.keywords or []:
                    if kw.arg in {"callback", "handler"} and isinstance(kw.value, _ast.Name):
                        cb = kw.value.id
                if cb in dropped:
                    return None  # drop statement
                return node

        fixed_tree = _HandlerPruner().visit(fixed_tree)
        _ast.fix_missing_locations(fixed_tree)
        try:
            main2 = _ast.unparse(fixed_tree) + "\n"
        except Exception:
            notes.append("ast_unparse_failed_keep_original")
            main2 = None
        if main2 is not None:
            from telegram_bot_engine.services.safe_fs import safe_write_under_root
            safe_write_under_root(root, main_p, main2)

    # menu_shop requires market service (existence check only — no regex)
    if "menu_shop" in defined:
        market = root / "app" / "services" / "market.py"
        if not market.exists():
            market.parent.mkdir(parents=True, exist_ok=True)
            try:
                from telegram_bot_engine.services.safe_fs import safe_write_under_root
                safe_write_under_root(root, market, _emit_market().rstrip() + "\n")
                notes.append("emitted_missing_market_service")
            except Exception:
                from telegram_bot_engine.services.safe_fs import safe_write_under_root
                safe_write_under_root(
                    root,
                    market,
                    '"""Auto-stub market service (generated)."""\n'
                    "def catalog(*a, **k):\n    return \'shop unavailable\'\n",
                )
                notes.append("stubbed_missing_market_service")
    return notes


def _ensure_referenced_service_stubs(root: Path, files_written: list[str]) -> list[str]:
    """If any generated module imports a missing service, write a safe implementation."""
    import ast as _ast
    from telegram_bot_engine.services.safe_fs import safe_write_under_root, safe_ident, UnsafePathError
    notes: list[str] = []
    root = Path(root)
    needed: set[str] = set()
    for path in root.rglob("*.py"):
        if "__pycache__" in path.parts or ".venv" in path.parts:
            continue
        try:
            tree = _ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError):
            continue
        for node in _ast.walk(tree):
            if not isinstance(node, _ast.ImportFrom):
                continue
            mod = node.module or ""
            if mod == "app.services":
                for alias in node.names:
                    if alias.name and alias.name != "*":
                        needed.add(alias.name)
            elif mod.startswith("app.services."):
                parts = mod.split(".")
                if len(parts) >= 3 and parts[2]:
                    needed.add(parts[2])
    services_dir = root / "app" / "services"
    services_dir.mkdir(parents=True, exist_ok=True)

    def _write(name: str, content: str, tag: str) -> None:
        from telegram_bot_engine.services.safe_fs import safe_ident, safe_write_text, UnsafePathError
        try:
            ident = safe_ident(name)
        except UnsafePathError:
            notes.append(f"skipped_bad_service_name:{name[:40]}")
            return
        rel = f"app/services/{ident}.py"
        target = root / rel
        if target.is_file():
            return
        try:
            safe_write_text(root, rel, content.rstrip() + "\n")
        except UnsafePathError as exc:
            notes.append(f"stub_write_rejected:{ident}:{exc}")
            return
        files_written.append(str(root / rel))
        notes.append(f"{tag}:{ident}")

    for name in sorted(needed):
        if name in {"i18n"}:
            continue
        target = services_dir / f"{name}.py"
        if target.is_file():
            continue
        # Root reliability: never emit dead stubs — working lean services only
        try:
            if name == "generic":
                content = _emit_lean_generic_service()
            else:
                content = _emit_lean_named_service(name)
        except Exception:
            content = _emit_lean_named_service(name)
        _write(name, content, "lean_service")

    if "app.flow_engine" in src or "from app.flow_engine" in src:
        fe = root / "app" / "flow_engine.py"
        if not fe.is_file():
            safe_write_under_root(root, fe, 
                '''"""Minimal flow engine stub — multi-step flows not enabled for this bot."""
from __future__ import annotations
from typing import Any

def active_flow(context: Any) -> bool:
    return bool(getattr(context, "user_data", {}) and context.user_data.get("flow"))

async def handle_text(update: Any, context: Any) -> bool:
    return False

async def handle_photo(update: Any, context: Any) -> bool:
    return False

async def handle_callback(update: Any, context: Any) -> bool:
    return False

def start_flow(*args: Any, **kwargs: Any) -> None:
    return None

def clear_flow(context: Any) -> None:
    if getattr(context, "user_data", None) is not None:
        context.user_data.pop("flow", None)
'''.rstrip()
                + "\n",
                encoding="utf-8",
            )
            files_written.append(str(fe))
            notes.append("stub_minimal:flow_engine")
    return notes
