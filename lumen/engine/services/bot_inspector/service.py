"""Structural inspection of a generated Telegram bot project.

Deterministic (no LLM): AST + file layout → commands, handlers, gaps, risks.
Used by chat (Groq) so the model can discuss the *real* bot, and by the
refine path before Gemini→engine regeneration.
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_IMPORTANT_FILES = (
    "main.py",
    "handlers.py",
    "requirements.txt",
    "config.py",
    "README.md",
    "bot_spec.json",
    "spec.json",
)


@dataclass
class BotInspection:
    path: str
    exists: bool = False
    files: list[str] = field(default_factory=list)
    commands: list[str] = field(default_factory=list)
    handler_fns: list[str] = field(default_factory=list)
    features_hint: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    entry: str = ""
    size_bytes: int = 0
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def chat_brief(self, *, max_weak: int = 8) -> str:
        if not self.exists:
            return "لا يوجد مشروع بوت محفوظ لهذا المستخدم بعد."
        lines = [
            f"مسار البوت: {self.path}",
            f"الملفات: {', '.join(self.files[:20]) or '—'}",
            f"الأوامر المسجّلة: {', '.join('/'+c for c in self.commands[:30]) or '—'}",
        ]
        if self.strengths:
            lines.append("نقاط قوة: " + "؛ ".join(self.strengths[:5]))
        if self.weaknesses:
            lines.append("نقاط ضعف محتملة: " + "؛ ".join(self.weaknesses[:max_weak]))
        return "\n".join(lines)


def _collect_commands(tree: ast.AST) -> list[str]:
    cmds: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = ""
        if isinstance(func, ast.Name):
            name = func.id
        elif isinstance(func, ast.Attribute):
            name = func.attr
        if name != "CommandHandler" or not node.args:
            continue
        a0 = node.args[0]
        if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
            cmds.append(a0.value)
        elif isinstance(a0, ast.List):
            for el in a0.elts:
                if isinstance(el, ast.Constant) and isinstance(el.value, str):
                    cmds.append(el.value)
    # dedupe stable
    seen: set[str] = set()
    out: list[str] = []
    for c in cmds:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _collect_handler_fns(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith("handle_") or node.name in {"start", "help", "error_handler"}:
                names.append(node.name)
    return sorted(set(names))


def _weaknesses(
    *,
    commands: list[str],
    files: list[str],
    handler_fns: list[str],
    main_src: str,
) -> tuple[list[str], list[str]]:
    weak: list[str] = []
    strong: list[str] = []
    cmd_set = set(commands)
    if "start" in cmd_set and "help" in cmd_set:
        strong.append("أوامر start/help موجودة")
    else:
        weak.append("ناقص /start أو /help")
    if len(commands) < 3:
        weak.append("عدد الأوامر قليل — البوت قد يبدو ناقصًا للمستخدم")
    else:
        strong.append(f"{len(commands)} أمر مسجّل")
    if "handlers.py" in files or any(n.startswith("handle_") for n in handler_fns):
        strong.append("handlers مفصولة أو مسماة بوضوح")
    if "requirements.txt" not in files:
        weak.append("لا يوجد requirements.txt")
    if "error_handler" not in handler_fns and "error_handler" not in main_src:
        weak.append("لا يظهر معالج أخطاء عام (error handler)")
    # commands without obvious handler name
    for c in commands:
        if c in {"start", "help", "cancel", "lang", "language"}:
            continue
        # soft check only
        if f"handle_{c}" not in handler_fns and not any(c in h for h in handler_fns):
            # not always a bug (aliases share handlers)
            pass
    if "TODO" in main_src or "NotImplemented" in main_src:
        weak.append("يوجد TODO أو NotImplemented في الكود")
    if "pass\n" in main_src and main_src.count("    pass") > 3:
        weak.append("دوال كثيرة فارغة (pass) — منطق ناقص محتمل")
    if not weak:
        strong.append("لا توجد مؤشرات ضعف هيكلية واضحة من الفحص الثابت")
    return weak, strong


def inspect_bot_project(project_path: str | Path | None) -> BotInspection:
    path = Path(str(project_path or "")).expanduser()
    insp = BotInspection(path=str(path) if project_path else "")
    if not project_path or not path.is_dir():
        return insp
    insp.exists = True
    files = []
    size = 0
    for p in sorted(path.rglob("*")):
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts:
            rel = p.relative_to(path).as_posix()
            if rel.count("/") <= 2:
                files.append(rel)
            try:
                size += p.stat().st_size
            except OSError:
                pass
    insp.files = files[:80]
    insp.size_bytes = size
    entry = "main.py" if (path / "main.py").is_file() else ""
    if not entry:
        for cand in ("bot.py", "app.py"):
            if (path / cand).is_file():
                entry = cand
                break
    insp.entry = entry
    commands: list[str] = []
    handlers: list[str] = []
    main_src = ""
    for py_name in (entry, "handlers.py", "handlers/__init__.py"):
        if not py_name:
            continue
        fp = path / py_name
        if not fp.is_file():
            continue
        try:
            src = fp.read_text(encoding="utf-8", errors="replace")
            if py_name == entry:
                main_src = src
            tree = ast.parse(src)
            commands.extend(_collect_commands(tree))
            handlers.extend(_collect_handler_fns(tree))
        except Exception as exc:
            insp.notes.append(f"parse {py_name}: {type(exc).__name__}")
    # dedupe commands
    seen: set[str] = set()
    uniq: list[str] = []
    for c in commands:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    insp.commands = uniq
    insp.handler_fns = sorted(set(handlers))
    # features from bot_spec.json if present
    for spec_name in ("bot_spec.json", "spec.json"):
        sp = path / spec_name
        if sp.is_file():
            try:
                import json

                data = json.loads(sp.read_text(encoding="utf-8"))
                feats = data.get("features") or data.get("features_requested") or []
                if isinstance(feats, list):
                    insp.features_hint = [
                        str(x.get("feature") if isinstance(x, dict) else x)[:64]
                        for x in feats
                    ][:40]
            except Exception:
                pass
            break
    weak, strong = _weaknesses(
        commands=insp.commands,
        files=insp.files,
        handler_fns=insp.handler_fns,
        main_src=main_src,
    )
    insp.weaknesses = weak
    insp.strengths = strong
    return insp


def resolve_user_bot_path(
    *,
    user_data: dict[str, Any] | None = None,
    explicit_path: str = "",
) -> str:
    """Best-effort path to the user's last/active generated bot."""
    if explicit_path and Path(explicit_path).is_dir():
        return explicit_path
    ud = user_data or {}
    for key in ("last_project_path", "active_bot_path"):
        p = str(ud.get(key) or "").strip()
        if p and Path(p).is_dir():
            return p
    active = ud.get("active_repo")
    if isinstance(active, dict):
        p = str(active.get("path") or "").strip()
        if p and Path(p).is_dir():
            return p
    pending = ud.get("pending_run") or ud.get("last_generate_result")
    if isinstance(pending, dict):
        p = str(pending.get("project_path") or "").strip()
        if p and Path(p).is_dir():
            return p
    return ""


__all__ = [
    "BotInspection",
    "inspect_bot_project",
    "resolve_user_bot_path",
]
