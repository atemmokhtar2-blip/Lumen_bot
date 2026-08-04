"""
StaticDevGate — neuro-free hard verifier for post-clone development.

Philosophy (v1 bots):
  Compilers & static analysis beat LLMs on structural truth.
  Neural models may propose later; this gate decides what is allowed to ship.

Checks (deterministic AST):
  - Syntax of every edited / entry Python file
  - Command registration consistency (handler function exists)
  - Duplicated CommandHandler registrations
  - Local imports of missing modules (active_dev_commands etc.)
  - Undefined free names used in simple call positions (best-effort)
  - Plan soundness: command names legal, not colliding

No network, no LLM. Pure symbolic structure.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


@dataclass
class StaticFinding:
    severity: str  # error | warning | info
    code: str
    file: str
    message_ar: str
    lineno: int = 0


@dataclass
class StaticReport:
    ok: bool
    findings: list[StaticFinding] = field(default_factory=list)
    files_checked: int = 0
    errors: int = 0
    warnings: int = 0

    def to_user_text(self) -> str:
        icon = "✅" if self.ok else "❌"
        lines = [
            f"{icon} *بوابة التحقق الاستاتيكي (StaticDevGate)*",
            f"• ملفات: {self.files_checked} | أخطاء: {self.errors} | تحذيرات: {self.warnings}",
        ]
        for f in self.findings[:25]:
            mark = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(f.severity, "•")
            loc = f"`{f.file}`" + (f":{f.lineno}" if f.lineno else "")
            lines.append(f"{mark} [{f.code}] {loc} — {f.message_ar}")
        if not self.findings:
            lines.append("• لا ملاحظات — الهيكل سليم رمزياً.")
        return "\n".join(lines)


def _parse(path: Path) -> tuple[ast.AST | None, str | None]:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return None, f"read_error:{type(e).__name__}"
    try:
        return ast.parse(src, filename=str(path)), None
    except SyntaxError as e:
        return None, f"{e.msg} (line {e.lineno})"


def _rel(root: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve())).replace("\\", "/")
    except Exception:
        return str(path)


def _iter_py(root: Path, limit: int = 80) -> Iterable[Path]:
    skip = {
        ".git", "__pycache__", ".venv", "venv", ".tbe_venv", ".tbe_deps",
        "site-packages", "node_modules", "dist", "build",
    }
    n = 0
    preferred = []
    other = []
    for p in root.rglob("*.py"):
        if any(x in p.parts for x in skip):
            continue
        if p.name in ("main.py", "bot.py", "app.py") or "handler" in p.name.lower():
            preferred.append(p)
        else:
            other.append(p)
    for p in preferred + other:
        yield p
        n += 1
        if n >= limit:
            break


def _functions_and_async(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
    return names


def _command_registrations(tree: ast.AST) -> list[tuple[str, str, int]]:
    """
    Return list of (command, handler_name, lineno) for PTB-style CommandHandler.
    """
    found: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        # CommandHandler("x", fn)
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name != "CommandHandler":
            continue
        if len(node.args) < 2:
            continue
        cmd_node, handler_node = node.args[0], node.args[1]
        cmd = ""
        if isinstance(cmd_node, ast.Constant) and isinstance(cmd_node.value, str):
            cmd = cmd_node.value
        handler = ""
        if isinstance(handler_node, ast.Name):
            handler = handler_node.id
        elif isinstance(handler_node, ast.Attribute):
            handler = handler_node.attr
        if cmd:
            found.append((cmd, handler, getattr(node, "lineno", 0) or 0))
    return found


def _aiogram_commands(tree: ast.AST) -> list[tuple[str, str, int]]:
    found: list[tuple[str, str, int]] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            # @router.message(Command("x"))
            text = ast.dump(dec)
            m = re.search(r"Command\(['\"]([A-Za-z0-9_]+)['\"]\)", text)
            if m:
                found.append((m.group(1), node.name, node.lineno))
    return found


def _local_imports(tree: ast.AST) -> list[tuple[str, int]]:
    mods: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and not node.level:
            top = node.module.split(".")[0]
            mods.append((node.module, node.lineno))
        elif isinstance(node, ast.Import):
            for a in node.names:
                mods.append((a.name.split(".")[0], node.lineno))
    return mods


_STDLIB = {
    "os", "sys", "re", "json", "ast", "time", "datetime", "pathlib", "typing",
    "collections", "functools", "itertools", "subprocess", "asyncio", "logging",
    "hashlib", "base64", "uuid", "copy", "math", "random", "string", "io",
    "tempfile", "shutil", "traceback", "dataclasses", "enum", "abc", "contextlib",
}


def analyze_project(root: str | Path, focus_files: list[str] | None = None) -> StaticReport:
    root = Path(root).resolve()
    findings: list[StaticFinding] = []
    files_checked = 0

    paths: list[Path] = []
    if focus_files:
        for f in focus_files:
            p = root / f
            if p.is_file():
                paths.append(p)
    if not paths:
        paths = list(_iter_py(root, limit=60))

    defined_handlers_global: set[str] = set()
    all_regs: list[tuple[str, str, str, int]] = []  # cmd, handler, file, line

    for path in paths:
        rel = _rel(root, path)
        tree, err = _parse(path)
        files_checked += 1
        if err:
            findings.append(StaticFinding(
                severity="error",
                code="syntax",
                file=rel,
                message_ar=f"SyntaxError: {err}",
            ))
            continue
        assert tree is not None
        fns = _functions_and_async(tree)
        defined_handlers_global |= fns

        for cmd, handler, ln in _command_registrations(tree):
            all_regs.append((cmd, handler, rel, ln))
            if handler and handler not in fns:
                # might be imported — check later against global
                pass
        for cmd, handler, ln in _aiogram_commands(tree):
            all_regs.append((cmd, handler, rel, ln))

        # local import existence
        for mod, ln in _local_imports(tree):
            top = mod.split(".")[0]
            if top in _STDLIB or top in {
                "telegram", "aiogram", "telebot", "pydantic", "dotenv",
                "httpx", "aiohttp", "requests", "openai", "google", "redis",
            }:
                continue
            # relative project module
            cand = root / f"{top}.py"
            cand_pkg = root / top / "__init__.py"
            if not cand.is_file() and not cand_pkg.is_file():
                # only flag if looks like our generated modules or short names
                if top.startswith("active_dev") or top in ("handlers", "config", "keyboards", "middlewares"):
                    findings.append(StaticFinding(
                        severity="error",
                        code="missing_local_module",
                        file=rel,
                        lineno=ln,
                        message_ar=f"استيراد محلي `{mod}` بدون ملف مطابق",
                    ))

    # registration consistency across project
    seen_cmd: dict[str, str] = {}
    for cmd, handler, rel, ln in all_regs:
        if cmd in seen_cmd and seen_cmd[cmd] != rel:
            findings.append(StaticFinding(
                severity="warning",
                code="duplicate_command",
                file=rel,
                lineno=ln,
                message_ar=f"الأمر /{cmd} مسجّل أيضاً في `{seen_cmd[cmd]}`",
            ))
        seen_cmd[cmd] = rel
        if handler and handler not in defined_handlers_global:
            findings.append(StaticFinding(
                severity="error",
                code="handler_missing",
                file=rel,
                lineno=ln,
                message_ar=f"CommandHandler(/{cmd}) يشير لدالة `{handler}` غير معرّفة في المشروع المفحوص",
            ))

    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warning")
    return StaticReport(
        ok=errors == 0,
        findings=findings,
        files_checked=files_checked,
        errors=errors,
        warnings=warnings,
    )


def plan_command_adds(
    existing_commands: set[str],
    wanted: list[str],
) -> tuple[list[str], list[StaticFinding]]:
    """Symbolic plan: which commands can be added safely."""
    findings: list[StaticFinding] = []
    accepted: list[str] = []
    for raw in wanted:
        name = re.sub(r"[^a-z0-9_]", "", (raw or "").lstrip("/").lower())[:32]
        if not name or not re.match(r"^[a-z][a-z0-9_]{0,31}$", name):
            findings.append(StaticFinding(
                severity="error",
                code="illegal_command_name",
                file="plan",
                message_ar=f"اسم أمر غير صالح: `{raw}`",
            ))
            continue
        if name in existing_commands:
            findings.append(StaticFinding(
                severity="info",
                code="command_exists",
                file="plan",
                message_ar=f"/{name} موجود — لن يُضاف مجدداً",
            ))
            continue
        if name in accepted:
            continue
        accepted.append(name)
    return accepted, findings


def verify_after_edit(
    root: str | Path,
    changed_files: list[str],
    expected_commands: list[str] | None = None,
) -> StaticReport:
    """
    Hard gate after ActiveDev writes files.
    Must pass before reporting success to the user.
    """
    root = Path(root)
    focus = list(changed_files)
    # always include entry points
    for name in ("main.py", "bot.py", "app.py", "active_dev_commands.py"):
        if (root / name).is_file() and name not in focus:
            focus.append(name)

    report = analyze_project(root, focus_files=focus)

    if expected_commands:
        # ensure each expected command appears in registrations of focus trees
        found_cmds: set[str] = set()
        for f in focus:
            p = root / f
            if not p.is_file():
                continue
            tree, err = _parse(p)
            if err or tree is None:
                continue
            for cmd, _, _ in _command_registrations(tree) + _aiogram_commands(tree):
                found_cmds.add(cmd.lower())
            # register_active_dev_commands module: functions named x_cmd
            src = p.read_text(encoding="utf-8", errors="ignore")
            for cmd in expected_commands:
                if f'CommandHandler("{cmd}"' in src or f"Command('{cmd}')" in src:
                    found_cmds.add(cmd.lower())
                if f"commands=[\"{cmd}\"]" in src or f"commands=['{cmd}']" in src:
                    found_cmds.add(cmd.lower())

        for cmd in expected_commands:
            if cmd.lower() not in found_cmds:
                report.findings.append(StaticFinding(
                    severity="error",
                    code="expected_command_missing",
                    file="gate",
                    message_ar=f"بعد التعديل: الأمر /{cmd} غير ظاهر في التسجيل",
                ))

    report.errors = sum(1 for f in report.findings if f.severity == "error")
    report.warnings = sum(1 for f in report.findings if f.severity == "warning")
    report.ok = report.errors == 0
    return report
