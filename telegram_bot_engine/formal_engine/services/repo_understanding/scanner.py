"""
Deep Repo Scanner v3 — production-grade deterministic understanding.

Goals:
  - Correctly detect Telegram bots across PTB / aiogram / telebot / pyrogram
  - Distinguish application bot vs library/framework package
  - Extract real registered commands (not noise)
  - Read README purpose
  - Architecture layers + quality signals
Uses: stdlib ast + filesystem only (no LLM).
"""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from ...schemas.repo_contract import (
    ClassInfo,
    CodeGraph,
    DeepFunction,
    DetectedCommand,
    DetectedHandler,
    EntryPoint,
    EnvVarInfo,
    FileEntry,
    FunctionInfo,
    LayerInfo,
    ModuleInfo,
    RepoContract,
)

_SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".tox",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs", ".idea",
    ".vscode", "htmlcov", ".ruff_cache", "docs", "examples", "example",
    "tests", "test", ".github", "site-packages", "dist-info",
}

_ENTRY_NAMES = {
    "main.py": 100,
    "bot.py": 95,
    "app.py": 85,
    "run.py": 80,
    "server.py": 75,
    "app/main.py": 95,
    "src/main.py": 90,
    "src/bot.py": 92,
    "__main__.py": 70,
}

_FW = {
    "python-telegram-bot": "python-telegram-bot",
    "telegram": "python-telegram-bot",
    "aiogram": "aiogram",
    "telebot": "pyTelegramBotAPI",
    "pytelegrambotapi": "pyTelegramBotAPI",
    "pyrogram": "pyrogram",
    "fastapi": "fastapi",
    "flask": "flask",
    "django": "django",
    "pydantic": "pydantic",
    "sqlalchemy": "sqlalchemy",
    "redis": "redis",
    "aiohttp": "aiohttp",
    "httpx": "httpx",
}

_LAYER_ROLES = {
    "formal_engine": "formal understanding + codegen",
    "engines": "generation engines",
    "generators": "concrete generators",
    "pipeline": "pipeline orchestration",
    "core": "contracts / bootstrap",
    "handlers": "telegram handlers",
    "services": "domain services",
    "configuration": "config",
    "ontology": "knowledge / rules",
    "understanding": "requirement understanding",
    "generation": "code generation",
    "schemas": "typed contracts",
    "app": "application package",
}


def _iter_files(root: Path, include_tests: bool = False) -> Iterable[Path]:
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        parts = set(p.parts)
        if parts & _SKIP_DIRS:
            # still allow requirements/readme at root-ish
            if p.name.lower() in ("requirements.txt", "pyproject.toml", "readme.md", "readme.rst"):
                if ".git" not in p.parts:
                    yield p
            continue
        if not include_tests and ("tests" in p.parts or "test" in p.parts):
            if p.suffix == ".py":
                continue
        yield p


def _kind(path: Path) -> str:
    name = path.name.lower()
    suf = path.suffix.lower()
    if suf == ".py":
        return "python"
    if name in ("requirements.txt", "pyproject.toml", "setup.cfg", "setup.py", "Pipfile"):
        return "config"
    if name.startswith("readme"):
        return "docs"
    if suf in (".yml", ".yaml", ".toml", ".json", ".env", ".ini"):
        return "config"
    return "other"


def _read(path: Path, limit: int = 350_000) -> str:
    try:
        return path.read_bytes()[:limit].decode("utf-8", errors="ignore")
    except Exception:
        return ""


def _parse_ast(path: Path) -> ast.AST | None:
    src = _read(path)
    if not src.strip():
        return None
    try:
        return ast.parse(src, filename=str(path))
    except SyntaxError:
        return None


def _base(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _call_name(node: ast.Call) -> str:
    return _base(node.func)


def _const_str(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _decorator_chain(dec: ast.expr) -> str:
    """Return dotted-ish name for decorator, e.g. router.message / bot.message_handler."""
    if isinstance(dec, ast.Call):
        return _decorator_chain(dec.func)
    if isinstance(dec, ast.Attribute):
        left = _decorator_chain(dec.value) if isinstance(dec.value, (ast.Attribute, ast.Name)) else ""
        return f"{left}.{dec.attr}" if left else dec.attr
    if isinstance(dec, ast.Name):
        return dec.id
    return ""


def _parse_requirements(root: Path) -> list[str]:
    deps: list[str] = []
    for fname in ("requirements.txt", "requirements-dev.txt"):
        f = root / fname
        if f.exists():
            for line in _read(f).splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                pkg = re.split(r"[<>=!;\\[\s]", line, maxsplit=1)[0].strip().lower()
                if pkg:
                    deps.append(pkg)
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        text = _read(pyproject)
        # project.dependencies style
        for m in re.finditer(r'^\s*["\']([A-Za-z0-9_.\-]+)["\']\s*[>=<~!]', text, re.M):
            deps.append(m.group(1).lower())
        for m in re.finditer(r'^\s*([A-Za-z0-9_.\-]+)\s*=\s*["\']', text, re.M):
            # poetry style optional — skip tools
            pass
    seen, out = set(), []
    for d in deps:
        if d not in seen:
            seen.add(d)
            out.append(d)
    return out[:60]


def _readme_purpose(root: Path) -> str:
    for name in ("README.md", "README.rst", "README.txt", "README"):
        p = root / name
        if not p.exists():
            continue
        text = _read(p, 20_000)
        # first meaningful paragraph
        lines = []
        for line in text.splitlines():
            s = line.strip()
            if not s or s.startswith("#") and len(s) < 4:
                continue
            if s.startswith("#"):
                s = s.lstrip("#").strip()
            if s.startswith("!") or s.startswith("[") or s.startswith("---"):
                continue
            if len(s) >= 20:
                lines.append(s)
            if len(lines) >= 3:
                break
        purpose = " ".join(lines)[:400]
        return purpose
    return ""


def _looks_like_library(root: Path, deps: list[str], py_count: int) -> bool:
    """Heuristic: packaging layout without a runnable bot entry."""
    signals = 0
    if (root / "setup.py").exists() or (root / "setup.cfg").exists():
        signals += 1
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        t = _read(pyproject).lower()
        if "[project]" in t or "[tool.poetry]" in t:
            signals += 1
        if "name" in t and ("aiogram" in t or "telegram" in t or "telebot" in t):
            signals += 2
    # many modules under package name matching framework
    pkg_dirs = [p for p in root.iterdir() if p.is_dir() and (p / "__init__.py").exists()]
    for d in pkg_dirs:
        if d.name in ("aiogram", "telegram", "telebot", "pyrogram", "ptb"):
            signals += 3
    # no main/bot at root and huge file count
    if py_count > 80 and not (root / "main.py").exists() and not (root / "bot.py").exists():
        signals += 1
    return signals >= 3


class _FileAnalysis:
    __slots__ = (
        "rel", "imports", "classes", "functions", "commands", "handlers",
        "env_vars", "tg_score", "fw_hits", "lines", "has_async", "has_typing",
        "is_entry_candidate", "deep_functions", "deep_class_count", "syntax_error",
    )

    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.imports: list[str] = []
        self.classes: list[ClassInfo] = []
        self.functions: list[FunctionInfo] = []
        self.commands: list[DetectedCommand] = []
        self.handlers: list[DetectedHandler] = []
        self.env_vars: list[EnvVarInfo] = []
        self.tg_score = 0
        self.fw_hits: set[str] = set()
        self.lines = 0
        self.has_async = False
        self.has_typing = False
        self.is_entry_candidate = False
        self.deep_functions: list[DeepFunction] = []
        self.deep_class_count = 0
        self.syntax_error: str = ""


def _add_cmd(
    out: list[DetectedCommand],
    name: str,
    rel: str,
    evidence: str,
    registration: str,
) -> None:
    name = (name or "").lstrip("/").lower().strip()
    if not name or len(name) > 32:
        return
    if not re.fullmatch(r"[a-z][a-z0-9_]{0,31}", name):
        return
    if name in ("name", "true", "false", "none", "self", "text", "command", "commands", "message"):
        return
    out.append(
        DetectedCommand(name=name, source_file=rel, evidence=evidence[:100], registration=registration)
    )



def _call_name_deep(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _call_name_deep(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        return _call_name_deep(node.func)
    if isinstance(node, ast.Subscript):
        return _call_name_deep(node.value)
    return ""


def _deep_index_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    an: _FileAnalysis,
    parent: str = "",
) -> None:
    """Record every function/method with its outbound calls (literal AST understanding)."""
    calls: list[str] = []
    seen: set[str] = set()
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            nm = _call_name_deep(n.func)
            if nm and nm not in seen:
                seen.add(nm)
                calls.append(nm)
            if len(calls) >= 50:
                break
    args = [a.arg for a in node.args.args if a.arg not in ("self", "cls")]
    decos: list[str] = []
    for d in node.decorator_list:
        dn = _call_name_deep(d) if not isinstance(d, ast.Call) else _call_name_deep(d.func)
        if not dn:
            dn = _decorator_chain(d)
        if dn:
            decos.append(dn)
    doc = ""
    try:
        doc = (ast.get_docstring(node) or "")[:160]
    except Exception:
        pass
    qual = f"{parent}.{node.name}" if parent else node.name
    an.deep_functions.append(
        DeepFunction(
            qualname=qual,
            file=an.rel,
            lineno=int(getattr(node, "lineno", 0) or 0),
            end_lineno=int(getattr(node, "end_lineno", 0) or getattr(node, "lineno", 0) or 0),
            is_async=isinstance(node, ast.AsyncFunctionDef),
            args=args[:16],
            decorators=decos[:10],
            calls=calls[:40],
            docstring=doc,
        )
    )


def _analyze_file(path: Path, root: Path) -> _FileAnalysis | None:
    tree = _parse_ast(path)
    if tree is None:
        return None
    rel = str(path.relative_to(root)).replace("\\", "/")
    an = _FileAnalysis(rel)
    an.lines = len(_read(path).splitlines())
    src = _read(path, 200_000)

    # quick framework hits from source text (complements imports)
    low = src.lower()
    if "aiogram" in low:
        an.fw_hits.add("aiogram")
        an.tg_score += 2
    if "python-telegram-bot" in low or "telegram.ext" in low:
        an.fw_hits.add("python-telegram-bot")
        an.tg_score += 2
    if "telebot" in low or "pytelegrambotapi" in low:
        an.fw_hits.add("pyTelegramBotAPI")
        an.tg_score += 2
    if "pyrogram" in low:
        an.fw_hits.add("pyrogram")
        an.tg_score += 2

    for node in tree.body:
        _visit_stmt(node, an)

    # Deep literal index: every function/method + outbound calls
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _deep_index_function(node, an)
        elif isinstance(node, ast.ClassDef):
            an.deep_class_count += 1
            for n in node.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    _deep_index_function(n, an, parent=node.name)
                elif isinstance(n, ast.ClassDef):  # nested class methods
                    an.deep_class_count += 1
                    for n2 in n.body:
                        if isinstance(n2, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            _deep_index_function(n2, an, parent=f"{node.name}.{n.name}")

    # walk all nodes for Call patterns
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            _visit_call(node, an)
        if isinstance(node, ast.Import):
            for a in node.names:
                root_mod = a.name.split(".")[0]
                an.imports.append(root_mod)
                _fw_from_import(root_mod, a.name, an)
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            root_mod = mod.split(".")[0]
            if root_mod:
                an.imports.append(root_mod)
                _fw_from_import(root_mod, mod, an)
            if "typing" in mod:
                an.has_typing = True

    if re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', src):
        an.is_entry_candidate = True
    if any(x in src for x in ("start_polling", "run_polling", "infinity_polling", "dp.start_polling", "application.run")):
        an.is_entry_candidate = True
        an.tg_score += 3

    return an


def _fw_from_import(root_mod: str, full: str, an: _FileAnalysis) -> None:
    full_l = full.lower()
    if root_mod in ("telegram",) or full_l.startswith("telegram."):
        an.fw_hits.add("python-telegram-bot")
        an.tg_score += 2
    if root_mod == "aiogram" or full_l.startswith("aiogram"):
        an.fw_hits.add("aiogram")
        an.tg_score += 2
    if root_mod in ("telebot",) or "telebot" in full_l:
        an.fw_hits.add("pyTelegramBotAPI")
        an.tg_score += 2
    if root_mod == "pyrogram":
        an.fw_hits.add("pyrogram")
        an.tg_score += 2


def _visit_stmt(node: ast.stmt, an: _FileAnalysis) -> None:
    if isinstance(node, ast.ClassDef):
        bases = [_base(b) for b in node.bases]
        methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        kind = "class"
        if any(b in ("BaseModel", "StrictModel", "BaseSettings") for b in bases):
            kind = "pydantic"
        elif node.name.endswith("Engine"):
            kind = "engine"
        elif node.name.endswith("Service"):
            kind = "service"
        an.classes.append(
            ClassInfo(name=node.name, file=an.rel, bases=[b for b in bases if b], methods=methods[:20], kind=kind)
        )
        for n in node.body:
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _visit_function(n, an, inside_class=True)
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        _visit_function(node, an, inside_class=False)


def _visit_function(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    an: _FileAnalysis,
    inside_class: bool,
) -> None:
    if isinstance(node, ast.AsyncFunctionDef):
        an.has_async = True
    decs = []
    for d in node.decorator_list:
        chain = _decorator_chain(d)
        decs.append(chain)
        _commands_from_decorator(d, chain, node.name, an)

    if not inside_class:
        an.functions.append(
            FunctionInfo(name=node.name, file=an.rel, is_async=isinstance(node, ast.AsyncFunctionDef), decorators=decs)
        )


def _commands_from_decorator(dec: ast.expr, chain: str, func_name: str, an: _FileAnalysis) -> None:
    chain_l = chain.lower()
    # telebot: @bot.message_handler(commands=['start', 'help'])
    if "message_handler" in chain_l:
        an.tg_score += 2
        an.handlers.append(DetectedHandler(kind="message", name=func_name, source_file=an.rel))
        if isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "commands":
                    _extract_command_list(kw.value, an, "telebot_decorator")
        return

    # aiogram: @router.message(Command("x")) or CommandStart()
    if chain_l.endswith(".message") or chain_l.endswith(".callback_query") or "router" in chain_l:
        an.tg_score += 2
        kind = "callback" if "callback" in chain_l else "message"
        an.handlers.append(DetectedHandler(kind=kind, name=func_name, source_file=an.rel))
        if isinstance(dec, ast.Call):
            for arg in list(dec.args) + [kw.value for kw in dec.keywords]:
                _extract_aiogram_filters(arg, an, func_name)
        # CommandStart on function name start
        if func_name in ("start", "start_handler", "cmd_start"):
            _add_cmd(an.commands, "start", an.rel, f"@{chain} def {func_name}", "aiogram_decorator")
        return

    # pyrogram style handlers
    if "on_message" in chain_l or "on_callback" in chain_l:
        an.tg_score += 2
        an.handlers.append(DetectedHandler(kind="message", name=func_name, source_file=an.rel))


def _extract_aiogram_filters(node: ast.expr, an: _FileAnalysis, func_name: str) -> None:
    if isinstance(node, ast.Call):
        name = _call_name(node)
        if name in ("CommandStart", "CommandHelp"):
            cmd = "start" if "Start" in name else "help"
            _add_cmd(an.commands, cmd, an.rel, f"{name}()", "aiogram_filter")
            return
        if name == "Command":
            # Command("products") or Command("a", "b")
            for a in node.args:
                s = _const_str(a)
                if s:
                    _add_cmd(an.commands, s, an.rel, f'Command("{s}")', "aiogram_filter")
                elif isinstance(a, (ast.List, ast.Tuple)):
                    for elt in a.elts:
                        s2 = _const_str(elt)
                        if s2:
                            _add_cmd(an.commands, s2, an.rel, f'Command("{s2}")', "aiogram_filter")
            return
        for a in node.args:
            _extract_aiogram_filters(a, an, func_name)
        for kw in node.keywords:
            _extract_aiogram_filters(kw.value, an, func_name)


def _extract_command_list(node: ast.expr, an: _FileAnalysis, reg: str) -> None:
    if isinstance(node, (ast.List, ast.Tuple)):
        for elt in node.elts:
            s = _const_str(elt)
            if s:
                _add_cmd(an.commands, s, an.rel, f"commands=['{s}']", reg)
    s = _const_str(node)
    if s:
        _add_cmd(an.commands, s, an.rel, f"commands='{s}'", reg)


def _visit_call(node: ast.Call, an: _FileAnalysis) -> None:
    fname = _call_name(node)

    # PTB: CommandHandler("start", ...)
    if fname == "CommandHandler":
        an.tg_score += 3
        an.handlers.append(DetectedHandler(kind="command", name="CommandHandler", source_file=an.rel))
        if node.args:
            s = _const_str(node.args[0])
            if s:
                _add_cmd(an.commands, s, an.rel, f'CommandHandler("{s}")', "CommandHandler")
            elif isinstance(node.args[0], (ast.List, ast.Tuple)):
                for elt in node.args[0].elts:
                    s2 = _const_str(elt)
                    if s2:
                        _add_cmd(an.commands, s2, an.rel, f'CommandHandler("{s2}")', "CommandHandler")

    if fname in ("CallbackQueryHandler", "MessageHandler", "ConversationHandler"):
        an.tg_score += 2
        kind = {
            "CallbackQueryHandler": "callback",
            "MessageHandler": "message",
            "ConversationHandler": "conversation",
        }[fname]
        an.handlers.append(DetectedHandler(kind=kind, name=fname, source_file=an.rel))

    if fname == "BotCommand" and node.args:
        s = _const_str(node.args[0])
        if s:
            _add_cmd(an.commands, s, an.rel, f'BotCommand("{s}")', "BotCommand")

    # aiogram include_router / start_polling
    if fname in ("include_router", "start_polling", "run_polling"):
        an.tg_score += 2

    # getenv
    if fname == "getenv" or (isinstance(node.func, ast.Attribute) and node.func.attr == "getenv"):
        if node.args:
            s = _const_str(node.args[0])
            if s and s.isupper():
                an.env_vars.append(EnvVarInfo(name=s, source_file=an.rel))


def _detect_layers(root: Path, py_files: list[Path]) -> list[LayerInfo]:
    counts: Counter[str] = Counter()
    for p in py_files:
        parts = p.relative_to(root).parts
        if not parts:
            continue
        if parts[0] == "telegram_bot_engine" and len(parts) >= 2:
            counts[parts[1]] += 1
        else:
            counts[parts[0]] += 1
    layers = []
    for name, cnt in counts.most_common(12):
        if name.endswith(".py"):
            continue
        layers.append(LayerInfo(name=name, path=name, file_count=cnt, role=_LAYER_ROLES.get(name, "")))
    return layers


class RepoUnderstandingService:
    def run(self, root_path: str | Path, remote_url: str = "") -> RepoContract:
        root = Path(root_path).resolve()
        if not root.exists() or not root.is_dir():
            return RepoContract(
                root_path=str(root), remote_url=remote_url, confidence=0.0,
                summary="المسار غير موجود", notes=["path_missing"],
            )

        files = list(_iter_files(root))
        py_files = [p for p in files if p.suffix == ".py"]
        all_py_including_tests = [
            p for p in root.rglob("*.py")
            if ".git" not in p.parts and "__pycache__" not in p.parts
        ]

        top_files = []
        for p in sorted(files, key=lambda x: x.stat().st_size if x.exists() else 0, reverse=True)[:25]:
            try:
                sz = p.stat().st_size
            except Exception:
                sz = 0
            top_files.append(FileEntry(path=str(p.relative_to(root)).replace("\\", "/"), size=sz, kind=_kind(p)))

        dirs = sorted({p.relative_to(root).parts[0] for p in files if p.relative_to(root).parts})[:25]
        languages = []
        if py_files or all_py_including_tests:
            languages.append("python")
        if any(p.suffix == ".js" for p in files):
            languages.append("javascript")

        deps = _parse_requirements(root)
        purpose = _readme_purpose(root)

        analyses: list[_FileAnalysis] = []
        # Full-repo AST pass (cap 400 modules) — deep function/call index in same walk
        import time as _time
        _t_index = _time.perf_counter()
        ranked = sorted(
            py_files,
            key=lambda p: (
                0 if p.name in ("main.py", "bot.py", "app.py") else 1,
                0 if "handler" in str(p).lower() else 1,
                0 if "test" not in str(p).lower() else 2,
                str(p),
            ),
        )
        for p in ranked[:400]:
            an = _analyze_file(p, root)
            if an:
                analyses.append(an)
        _index_ms = (_time.perf_counter() - _t_index) * 1000.0

        imports = Counter()
        commands_raw: list[DetectedCommand] = []
        handlers: list[DetectedHandler] = []
        classes: list[ClassInfo] = []
        functions: list[FunctionInfo] = []
        env_vars: list[EnvVarInfo] = []
        fw_hits: Counter[str] = Counter()
        tg_score = 0
        total_lines = 0
        has_async = has_typing = False

        for an in analyses:
            imports.update(an.imports)
            commands_raw.extend(an.commands)
            handlers.extend(an.handlers)
            classes.extend(an.classes)
            functions.extend(an.functions)
            env_vars.extend(an.env_vars)
            for h in an.fw_hits:
                fw_hits[h] += 1
            tg_score += an.tg_score
            total_lines += an.lines
            has_async = has_async or an.has_async
            has_typing = has_typing or an.has_typing

        # frameworks
        frameworks: list[str] = []
        for d in deps:
            key = d.lower().replace("_", "-")
            if key in _FW and _FW[key] not in frameworks:
                frameworks.append(_FW[key])
            if "telegram" in key and "python-telegram-bot" not in frameworks:
                if key in ("python-telegram-bot", "telegram"):
                    frameworks.append("python-telegram-bot")
        for name, _ in fw_hits.most_common():
            if name not in frameworks:
                frameworks.append(name)

        # command dedupe prefer stronger registration
        rank = {
            "CommandHandler": 5,
            "aiogram_filter": 5,
            "telebot_decorator": 5,
            "BotCommand": 4,
            "aiogram_decorator": 3,
            "def": 1,
        }
        cmd_map: dict[str, DetectedCommand] = {}
        for c in commands_raw:
            prev = cmd_map.get(c.name)
            if prev is None or rank.get(c.registration, 0) > rank.get(prev.registration, 0):
                cmd_map[c.name] = c
        commands = sorted(
            cmd_map.values(),
            key=lambda c: (0 if c.name in ("start", "help") else 1, c.name),
        )[:25]

        # handlers dedupe
        h_seen, handlers_u = set(), []
        for h in handlers:
            k = (h.kind, h.source_file, h.name)
            if k not in h_seen:
                h_seen.add(k)
                handlers_u.append(h)

        # entry points
        entries: list[EntryPoint] = []
        for rel, score in _ENTRY_NAMES.items():
            if (root / rel).exists():
                entries.append(EntryPoint(path=rel, reason="standard_name", score=score))
        for an in analyses:
            if an.is_entry_candidate and not any(e.path == an.rel for e in entries):
                score = 75 + min(an.tg_score, 20)
                entries.append(EntryPoint(path=an.rel, reason="runtime_entry", score=score))
        entries = sorted(entries, key=lambda e: -e.score)[:8]

        layers = _detect_layers(root, py_files)
        engines = sorted({c.name for c in classes if c.kind == "engine" and not c.name.startswith(("Base", "Fake"))})[:25]
        services = sorted({c.name for c in classes if c.kind == "service"})[:20]
        data_models = sorted({c.name for c in classes if c.kind == "pydantic"})[:25]

        is_library = _looks_like_library(root, deps, len(all_py_including_tests))
        is_gen = (root / "telegram_bot_engine").exists() or any(
            n in {c.name for c in classes} | {f.name for f in functions}
            for n in ("CodegenService", "UnderstandingService", "generate_bot", "PlanningService")
        )
        has_tg_fw = any(
            x in frameworks
            for x in ("aiogram", "python-telegram-bot", "pyTelegramBotAPI", "pyrogram")
        )
        # App bot if signals OR telegram framework in deps/entry (even if AST score low)
        is_tg_app = (not is_library) and (
            tg_score >= 2
            or bool(commands)
            or bool(handlers_u)
            or (has_tg_fw and (bool(entries) or bool(py_files)))
        )
        is_tg_lib = is_library and has_tg_fw

        if is_gen:
            style = "generation_engine"
            arch = "محرك توليد بوتات تليجرام (فهم → تخطيط → توليد)."
        elif is_tg_lib:
            style = "library"
            arch = f"مكتبة/إطار عمل تليجرام ({', '.join(frameworks[:3])}) — ليست بوت تطبيقي."
        elif is_tg_app:
            style = "telegram_bot"
            primary = frameworks[0] if frameworks else "telegram"
            arch = f"بوت تليجرام تطبيقي على {primary}."
        elif is_library:
            style = "library"
            arch = "حزمة/مكتبة Python."
        else:
            style = "modular" if layers else "unknown"
            arch = "مشروع Python عام."

        # confidence
        conf = 0.25
        if languages:
            conf += 0.1
        if is_tg_app or is_tg_lib or is_gen:
            conf += 0.2
        if commands:
            conf += 0.15
        if entries:
            conf += 0.1
        if frameworks:
            conf += 0.1
        if purpose:
            conf += 0.05
        if layers:
            conf += 0.05
        conf = round(min(0.99, conf), 3)

        notes = []
        if is_library and not is_tg_app:
            notes.append("classified_as_library_not_app")
        if is_tg_app and not commands:
            notes.append("telegram_app_but_no_commands_extracted")
        if not entries and is_tg_app:
            notes.append("no_clear_entry_point")

        if is_gen:
            summary = f"محرك توليد — {len(engines)} محرك، {len(commands)} أوامر واجهة."
        elif is_tg_lib:
            summary = f"مكتبة تليجرام ({', '.join(frameworks[:2])}) — ليس بوت جاهز للتشغيل كمنتج نهائي."
        elif is_tg_app:
            summary = f"بوت تليجرام — أوامر: {', '.join('/'+c.name for c in commands[:8]) or 'غير مستخرجة بعد'}."
        else:
            summary = f"مشروع Python — {len(classes)} صنف، {len(py_files)} ملف."
        if purpose:
            summary += f" | README: {purpose[:160]}"

        key_classes = sorted(
            classes,
            key=lambda c: (0 if c.kind in ("engine", "service") else 1 if c.kind == "pydantic" else 2, -len(c.methods), c.name),
        )[:20]
        key_functions = [
            f for f in functions
            if f.name in ("main", "generate_bot", "understand", "plan", "smart_clone", "understand_repo")
            or any(x in f.name for x in ("start", "handler", "poll"))
        ][:20]

        env_map = {e.name: e for e in env_vars if e.name.isupper()}
        modules_sample = []
        for an in sorted(analyses, key=lambda a: -a.lines)[:12]:
            modules_sample.append(
                ModuleInfo(
                    path=an.rel,
                    imports=sorted(set(an.imports))[:12],
                    classes=[c.name for c in an.classes][:8],
                    functions=[f.name for f in an.functions][:8],
                    lines=an.lines,
                )
            )

        has_tests = any(
            "tests" in str(p) or p.name.startswith("test_")
            for p in all_py_including_tests
        )

        # --- Code graph (literal: every indexed function + calls) ---
        all_deep: list[DeepFunction] = []
        mod_counts: dict[str, int] = {}
        call_edges = 0
        class_count = 0
        syntax_errors: list[str] = []
        for an in analyses:
            class_count += an.deep_class_count
            mod_counts[an.rel] = len(an.deep_functions)
            for df in an.deep_functions:
                all_deep.append(df)
                call_edges += len(df.calls)
            if an.syntax_error:
                syntax_errors.append(f"{an.rel}: {an.syntax_error}")
        # Prefer storing functions from entry/handler modules, then densest
        def _fn_rank(f: DeepFunction) -> tuple:
            p = f.file.lower()
            return (
                0 if any(x in p for x in ("main.py", "bot.py", "handler")) else 1,
                -len(f.calls),
                f.file,
                f.lineno,
            )
        stored = sorted(all_deep, key=_fn_rank)[:250]
        call_sample: dict[str, list[str]] = {}
        for f in stored[:80]:
            if f.calls:
                call_sample[f"{f.file}::{f.qualname}"] = f.calls[:20]
        code_graph = CodeGraph(
            modules_indexed=len(analyses),
            function_count=len(all_deep),
            class_count=class_count,
            call_edge_count=call_edges,
            lines_covered=total_lines,
            index_ms=round(_index_ms, 1),
            syntax_errors=syntax_errors[:20],
            functions=stored,
            call_graph_sample=call_sample,
            module_function_counts=dict(sorted(mod_counts.items(), key=lambda x: -x[1])[:40]),
        )

        return RepoContract(
            root_path=str(root),
            repo_name=root.name,
            remote_url=remote_url or "",
            languages=languages,
            frameworks=frameworks,
            architecture_style=style,
            entry_points=entries,
            commands=commands,
            handlers=handlers_u[:40],
            dependencies=deps,
            layers=layers,
            key_classes=key_classes,
            key_functions=key_functions,
            modules_sample=modules_sample,
            env_vars=list(env_map.values())[:25],
            data_models=data_models,
            services=services,
            engines=engines,
            file_count=len(files),
            python_file_count=len(py_files),
            total_lines=total_lines,
            top_files=top_files,
            top_dirs=dirs,
            is_telegram_bot=bool(is_tg_app),
            is_generation_engine=bool(is_gen),
            confidence=conf,
            summary=summary,
            architecture_summary=arch,
            notes=notes,
            quality_signals={
                "has_tests": has_tests,
                "has_typing": has_typing,
                "has_async": has_async,
                "tg_score": tg_score,
                "is_library": is_library,
                "readme_purpose": bool(purpose),
                "ast_files_scanned": len(analyses),
                "class_count": len(classes),
            },
            raw_stats={
                "top_imports": [n for n, _ in imports.most_common(12)],
                "fw_hits": dict(fw_hits),
                "purpose": purpose[:300],
                "deep_functions": len(all_deep),
                "deep_call_edges": call_edges,
            },
            code_graph=code_graph,
        )


def understand_repo(root_path: str | Path, remote_url: str = "") -> RepoContract:
    contract = RepoUnderstandingService().run(root_path, remote_url=remote_url)
    try:
        from ..repo_intelligence import enrich_repo_contract
        return enrich_repo_contract(contract)
    except Exception:
        return contract
