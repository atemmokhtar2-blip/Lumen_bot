"""Build AnalysisContext from a project root (one parse pass)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from .models import AnalysisContext, ModuleInfo

_SKIP = {
    ".git", "__pycache__", ".venv", "venv", ".tbe_venv", ".tbe_deps",
    "site-packages", "node_modules", "dist", "build", ".tox", ".mypy_cache",
}


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path)


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _extract_module_info(rel: str, source: str) -> ModuleInfo:
    info = ModuleInfo(path=rel, source=source)
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as e:
        info.syntax_error = f"{e.msg} (line {e.lineno})"
        return info
    info.tree = tree

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            info.functions.add(node.name)
        elif isinstance(node, ast.ClassDef):
            info.classes.add(node.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            info.imports.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for a in node.names:
                info.imports.append((a.name, node.lineno))

    # PTB CommandHandler("cmd", fn)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) != "CommandHandler":
            continue
        if len(node.args) < 2:
            continue
        cmd_n, h_n = node.args[0], node.args[1]
        cmd = cmd_n.value if isinstance(cmd_n, ast.Constant) and isinstance(cmd_n.value, str) else ""
        handler = ""
        if isinstance(h_n, ast.Name):
            handler = h_n.id
        elif isinstance(h_n, ast.Attribute):
            handler = h_n.attr
        if cmd:
            info.command_regs.append((cmd, handler, getattr(node, "lineno", 0) or 0, "ptb"))

    # aiogram @...Command("x")
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            dump = ast.dump(dec)
            m = re.search(r"Command\(['\"]([A-Za-z0-9_]+)['\"]\)", dump)
            if m:
                info.command_regs.append((m.group(1), node.name, node.lineno, "aiogram"))
            # telebot-ish in decorators
            m2 = re.search(
                r"commands\s*=\s*\[([^\]]+)\]",
                dump,
            )
            if m2:
                for cm in re.findall(r"['\"]([A-Za-z0-9_]+)['\"]", m2.group(1)):
                    info.command_regs.append((cm, node.name, node.lineno, "telebot"))

    # telebot message_handler(commands=[...]) via source scan backup
    for m in re.finditer(
        r"@bot\.message_handler\([^)]*commands\s*=\s*\[([^\]]+)\]",
        source,
    ):
        for cm in re.findall(r"['\"]([A-Za-z0-9_]+)['\"]", m.group(1)):
            info.command_regs.append((cm, "", 0, "telebot"))

    return info


def build_context(
    root: str | Path,
    focus_files: list[str] | None = None,
    limit: int = 80,
    expected_commands: list[str] | None = None,
) -> AnalysisContext:
    root_p = Path(root).resolve()
    ctx = AnalysisContext(
        root=str(root_p),
        focus_only=bool(focus_files),
        expected_commands=list(expected_commands or []),
    )

    paths: list[Path] = []
    if focus_files:
        for f in focus_files:
            p = root_p / f
            if p.is_file() and p.suffix == ".py":
                paths.append(p)

    if not paths:
        preferred: list[Path] = []
        other: list[Path] = []
        for p in root_p.rglob("*.py"):
            if any(x in p.parts for x in _SKIP):
                continue
            if p.name in ("main.py", "bot.py", "app.py") or "handler" in p.name.lower():
                preferred.append(p)
            else:
                other.append(p)
        paths = (preferred + other)[:limit]

    # local package/module names for import checks
    local: set[str] = set()
    for p in root_p.rglob("*"):
        if any(x in p.parts for x in _SKIP):
            continue
        if p.is_file() and p.suffix == ".py":
            local.add(p.stem)
            if p.name == "__init__.py" and p.parent != root_p:
                local.add(p.parent.name)
        elif p.is_dir() and (p / "__init__.py").exists():
            local.add(p.name)
    ctx.local_module_names = local

    for path in paths:
        rel = _rel(root_p, path)
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        info = _extract_module_info(rel, source)
        ctx.modules[rel] = info
        ctx.all_functions |= info.functions
        ctx.all_classes |= info.classes

    ctx.meta["module_count"] = len(ctx.modules)
    return ctx
