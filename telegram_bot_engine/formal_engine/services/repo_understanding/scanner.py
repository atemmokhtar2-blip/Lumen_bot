"""
Repo scanner — deterministic structural understanding of a local repository.

No LLM. Regex + filesystem + light AST-ish patterns.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from ...schemas.repo_contract import (
    DetectedCommand,
    DetectedHandler,
    EntryPoint,
    FileEntry,
    RepoContract,
)

_SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".tox",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
}

_CMD_PATTERNS = [
    re.compile(r'CommandHandler\s*\(\s*["\']([a-zA-Z0-9_]+)["\']', re.M),
    re.compile(r'commands?\s*=\s*\[\s*BotCommand\s*\(\s*["\']([a-zA-Z0-9_]+)["\']', re.M),
    re.compile(r'["\']/([a-zA-Z0-9_]{2,32})["\']', re.M),  # weak fallback
    re.compile(r'(?:async\s+)?def\s+(?:cmd_)?([a-z][a-z0-9_]{1,30})_handler\s*\(', re.M),
]

_HANDLER_PATTERNS = [
    (re.compile(r'CommandHandler\s*\(', re.M), "command"),
    (re.compile(r'CallbackQueryHandler\s*\(', re.M), "callback"),
    (re.compile(r'MessageHandler\s*\(', re.M), "message"),
    (re.compile(r'ConversationHandler\s*\(', re.M), "conversation"),
]

_ENTRY_CANDIDATES = (
    "main.py", "bot.py", "app.py", "run.py", "server.py",
    "app/main.py", "src/main.py", "src/bot.py",
)

_FRAMEWORK_HINTS = {
    "python-telegram-bot": "python-telegram-bot",
    "aiogram": "aiogram",
    "telebot": "pyTelegramBotAPI",
    "pyrogram": "pyrogram",
    "fastapi": "fastapi",
    "flask": "flask",
    "django": "django",
    "pydantic": "pydantic",
}


def _iter_files(root: Path) -> Iterable[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if any(part in _SKIP_DIRS for part in p.parts):
            continue
        yield p


def _kind(path: Path) -> str:
    name = path.name.lower()
    suf = path.suffix.lower()
    if suf == ".py":
        return "python"
    if name in ("requirements.txt", "pyproject.toml", "setup.cfg", "setup.py", "Pipfile"):
        return "config"
    if suf in (".md", ".rst", ".txt") and "test" not in name:
        return "docs"
    if "test" in name or path.parts and "tests" in path.parts:
        return "test"
    if suf in (".yml", ".yaml", ".toml", ".json", ".env", ".ini"):
        return "config"
    return "other"


def _read_text(path: Path, limit: int = 200_000) -> str:
    try:
        data = path.read_bytes()[:limit]
        return data.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _parse_requirements(root: Path) -> list[str]:
    deps: list[str] = []
    req = root / "requirements.txt"
    if req.exists():
        for line in _read_text(req).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            pkg = re.split(r"[<>=!;\\[]", line, maxsplit=1)[0].strip()
            if pkg:
                deps.append(pkg)
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = _read_text(pyproject)
        for m in re.finditer(r'["\']([A-Za-z0-9_.\\-]+)[>=<!~]', text):
            deps.append(m.group(1))
    # unique preserve order
    seen = set()
    out = []
    for d in deps:
        k = d.lower()
        if k not in seen:
            seen.add(k)
            out.append(d)
    return out[:40]


def _detect_frameworks(deps: list[str], all_text_sample: str) -> list[str]:
    found = []
    blob = " ".join(deps).lower() + "\n" + all_text_sample.lower()
    for needle, name in _FRAMEWORK_HINTS.items():
        if needle.lower() in blob and name not in found:
            found.append(name)
    return found


def _detect_entry_points(root: Path, py_files: list[Path]) -> list[EntryPoint]:
    entries: list[EntryPoint] = []
    for rel in _ENTRY_CANDIDATES:
        p = root / rel
        if p.exists():
            entries.append(EntryPoint(path=rel, reason="standard_name"))
    # if __name__ == "__main__" (skip tests)
    for p in py_files[:80]:
        rel = str(p.relative_to(root)).replace("\\", "/")
        if "test" in rel.lower() or rel.startswith("tests/"):
            continue
        text = _read_text(p, 50_000)
        if re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', text):
            if not any(e.path == rel for e in entries):
                entries.append(EntryPoint(path=rel, reason="__main__"))
    return entries[:8]


def _detect_commands_and_handlers(
    root: Path, py_files: list[Path]
) -> tuple[list[DetectedCommand], list[DetectedHandler], bool]:
    commands: list[DetectedCommand] = []
    handlers: list[DetectedHandler] = []
    seen_cmds: set[str] = set()
    is_tg = False

    # Only strong registration patterns — avoid false positives from random defs
    strong_cmd = [
        re.compile(r'CommandHandler\s*\(\s*["\']([a-zA-Z0-9_]+)["\']', re.M),
        re.compile(r'bot\.command\s*\(\s*["\']/([a-zA-Z0-9_]+)["\']', re.M),
        re.compile(r'@\w*\.command\s*\(\s*["\']/?([a-zA-Z0-9_]+)["\']', re.M),
        re.compile(r'BotCommand\s*\(\s*["\']([a-zA-Z0-9_]+)["\']', re.M),
    ]
    classic_handlers = re.compile(
        r'(?:async\s+)?def\s+(start|help|settings|admin|menu|status)(?:_handler|_cmd|_command)?\s*\(',
        re.M,
    )

    for p in py_files[:120]:
        text = _read_text(p, 150_000)
        rel = str(p.relative_to(root)).replace("\\", "/")
        low = text.lower()
        file_tg = any(
            x in low
            for x in ("python-telegram-bot", "telegram.ext", "aiogram", "telebot", "pyrogram")
        )
        if file_tg:
            is_tg = True

        for rx, kind in _HANDLER_PATTERNS:
            if rx.search(text):
                handlers.append(DetectedHandler(kind=kind, name=kind, source_file=rel))
                if kind == "command":
                    is_tg = True

        if not file_tg and "CommandHandler" not in text:
            continue

        for rx in strong_cmd:
            for m in rx.finditer(text):
                name = m.group(1).lower().lstrip("/")
                if name in seen_cmds or len(name) < 2:
                    continue
                if name in ("name", "true", "false", "none", "self", "text", "command"):
                    continue
                seen_cmds.add(name)
                commands.append(
                    DetectedCommand(name=name, source_file=rel, evidence=m.group(0)[:80])
                )

        if file_tg:
            for m in classic_handlers.finditer(text):
                name = m.group(1).lower()
                if name not in seen_cmds:
                    seen_cmds.add(name)
                    commands.append(
                        DetectedCommand(name=name, source_file=rel, evidence=m.group(0)[:80])
                    )

    def _key(c: DetectedCommand) -> tuple:
        pri = 0 if c.name in ("start", "help") else 1
        return (pri, c.name)

    commands = sorted(commands, key=_key)[:20]
    h_seen = set()
    h_out = []
    for h in handlers:
        k = (h.kind, h.source_file)
        if k not in h_seen:
            h_seen.add(k)
            h_out.append(h)
    return commands, h_out[:40], is_tg


def _summary(contract: RepoContract) -> str:
    if contract.is_telegram_bot:
        n = len(contract.commands)
        return f"مستودع يبدو كبوت تليجرام ({n} أوامر مكتشفة)."
    if "python" in contract.languages:
        return "مستودع Python؛ لم يُؤكد أنه بوت تليجرام."
    return "مستودع تم مسحه هيكلياً."


class RepoUnderstandingService:
    def run(self, root_path: str | Path, remote_url: str = "") -> RepoContract:
        root = Path(root_path).resolve()
        if not root.exists() or not root.is_dir():
            return RepoContract(
                root_path=str(root),
                remote_url=remote_url,
                confidence=0.0,
                summary="المسار غير موجود",
                notes=["path_missing"],
            )

        files = list(_iter_files(root))
        py_files = [p for p in files if p.suffix == ".py"]
        top_files = []
        for p in sorted(files, key=lambda x: x.stat().st_size if x.exists() else 0, reverse=True)[:25]:
            try:
                sz = p.stat().st_size
            except Exception:
                sz = 0
            top_files.append(
                FileEntry(path=str(p.relative_to(root)).replace("\\", "/"), size=sz, kind=_kind(p))
            )

        dirs = sorted(
            {
                str(p.relative_to(root)).replace("\\", "/").split("/")[0]
                for p in files
                if len(p.relative_to(root).parts) >= 1
            }
        )[:20]

        languages = []
        if py_files:
            languages.append("python")
        if any(p.suffix == ".js" for p in files):
            languages.append("javascript")
        if any(p.suffix == ".ts" for p in files):
            languages.append("typescript")

        deps = _parse_requirements(root)
        sample_parts = []
        for p in py_files[:15]:
            sample_parts.append(_read_text(p, 8000))
        frameworks = _detect_frameworks(deps, "\n".join(sample_parts))
        entries = _detect_entry_points(root, py_files)
        commands, handlers, is_tg = _detect_commands_and_handlers(root, py_files)

        confidence = 0.35
        if py_files:
            confidence += 0.15
        if is_tg:
            confidence += 0.25
        if commands:
            confidence += 0.1
        if entries:
            confidence += 0.1
        if deps:
            confidence += 0.05
        confidence = min(0.98, confidence)

        notes = []
        if not py_files:
            notes.append("no_python_files")
        if is_tg and not commands:
            notes.append("telegram_signals_but_no_commands")
        if not entries:
            notes.append("no_clear_entry_point")

        contract = RepoContract(
            root_path=str(root),
            repo_name=root.name,
            remote_url=remote_url or "",
            languages=languages,
            frameworks=frameworks,
            entry_points=entries,
            commands=commands,
            handlers=handlers,
            dependencies=deps,
            file_count=len(files),
            python_file_count=len(py_files),
            top_files=top_files,
            top_dirs=dirs,
            is_telegram_bot=is_tg,
            confidence=round(confidence, 3),
            notes=notes,
            raw_stats={
                "scanned_python_files": min(len(py_files), 120),
                "handler_kinds": sorted({h.kind for h in handlers}),
            },
        )
        contract.summary = _summary(contract)
        return contract


def understand_repo(root_path: str | Path, remote_url: str = "") -> RepoContract:
    return RepoUnderstandingService().run(root_path, remote_url=remote_url)
