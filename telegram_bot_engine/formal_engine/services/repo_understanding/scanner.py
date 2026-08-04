"""
Deep Repo Scanner v2 — AST + filesystem + architecture inference.

Deterministic. No LLM. Uses Python stdlib `ast` as the primary tool.
"""

from __future__ import annotations

import ast
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from ...schemas.repo_contract import (
    ClassInfo,
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
    ".vscode", "htmlcov", ".ruff_cache",
}

_ENTRY_NAMES = {
    "main.py": 100,
    "bot.py": 90,
    "app.py": 85,
    "run.py": 80,
    "server.py": 75,
    "app/main.py": 95,
    "src/main.py": 90,
    "src/bot.py": 88,
}

_FRAMEWORK_MAP = {
    "python-telegram-bot": "python-telegram-bot",
    "telegram": "python-telegram-bot",
    "aiogram": "aiogram",
    "telebot": "pyTelegramBotAPI",
    "pyrogram": "pyrogram",
    "fastapi": "fastapi",
    "flask": "flask",
    "django": "django",
    "pydantic": "pydantic",
    "sqlalchemy": "sqlalchemy",
    "redis": "redis",
    "celery": "celery",
    "httpx": "httpx",
    "aiohttp": "aiohttp",
}

_LAYER_ROLES = {
    "formal_engine": "formal understanding + codegen core",
    "engines": "generation engines",
    "generators": "concrete generator engines",
    "pipeline": "pipeline orchestration",
    "core": "contracts and bootstrap",
    "handlers": "telegram handlers",
    "services": "domain services",
    "tests": "test suite",
    "docs": "documentation",
    "configuration": "config system",
    "registry": "engine registry",
    "manager": "lifecycle manager",
    "builders": "file/module builders",
    "validators": "validators",
    "ontology": "knowledge / rules",
    "understanding": "requirement understanding",
    "generation": "code generation",
    "schemas": "typed contracts",
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
    if "test" in name or "tests" in path.parts:
        return "test"
    if suf in (".md", ".rst"):
        return "docs"
    if suf in (".yml", ".yaml", ".toml", ".json", ".env", ".ini"):
        return "config"
    return "other"


def _read(path: Path, limit: int = 400_000) -> str:
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


def _parse_requirements(root: Path) -> list[str]:
    deps: list[str] = []
    req = root / "requirements.txt"
    if req.exists():
        for line in _read(req).splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-"):
                continue
            pkg = re.split(r"[<>=!;\\[\s]", line, maxsplit=1)[0].strip()
            if pkg:
                deps.append(pkg)
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        for m in re.finditer(
            r'^\s*["\']([A-Za-z0-9_.\-]+)["\']\s*[>=<~!]',
            _read(pyproject),
            re.M,
        ):
            deps.append(m.group(1))
    seen, out = set(), []
    for d in deps:
        k = d.lower()
        if k not in seen:
            seen.add(k)
            out.append(d)
    return out[:50]


def _base_name(node: ast.expr) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _decorator_names(decs: list[ast.expr]) -> list[str]:
    names = []
    for d in decs:
        if isinstance(d, ast.Name):
            names.append(d.id)
        elif isinstance(d, ast.Attribute):
            names.append(d.attr)
        elif isinstance(d, ast.Call):
            names.append(_base_name(d.func))
    return names


class _ModuleAnalyzer(ast.NodeVisitor):
    def __init__(self, rel: str) -> None:
        self.rel = rel
        self.imports: list[str] = []
        self.classes: list[ClassInfo] = []
        self.functions: list[FunctionInfo] = []
        self.commands: list[DetectedCommand] = []
        self.handlers: list[DetectedHandler] = []
        self.env_vars: list[EnvVarInfo] = []
        self.is_tg = False
        self.has_async = False
        self.has_typing = False
        self.lines = 0

    def visit_Import(self, node: ast.Import) -> Any:
        for a in node.names:
            self.imports.append(a.name.split(".")[0])
            if a.name.startswith(("telegram", "aiogram", "telebot", "pyrogram")):
                self.is_tg = True
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> Any:
        mod = (node.module or "").split(".")[0]
        if mod:
            self.imports.append(mod)
        if (node.module or "").startswith(("telegram", "aiogram", "telebot")):
            self.is_tg = True
        if node.module and (
            "typing" in (node.module or "")
            or any(a.name in ("Optional", "List", "Dict", "Any") for a in node.names)
        ):
            self.has_typing = True
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        bases = [_base_name(b) for b in node.bases]
        methods = [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        decs = _decorator_names(node.decorator_list)
        kind = "class"
        if "BaseModel" in bases or "StrictModel" in bases or "BaseSettings" in bases:
            kind = "pydantic"
        elif "dataclass" in decs:
            kind = "dataclass"
        elif node.name.endswith("Engine") or "Engine" in bases:
            kind = "engine"
        elif node.name.endswith("Service"):
            kind = "service"
        self.classes.append(
            ClassInfo(
                name=node.name,
                file=self.rel,
                bases=[b for b in bases if b],
                methods=methods[:20],
                kind=kind,
            )
        )
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        self._fn(node, False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:
        self.has_async = True
        self._fn(node, True)

    def _fn(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool) -> None:
        decs = _decorator_names(node.decorator_list)
        self.functions.append(
            FunctionInfo(
                name=node.name,
                file=self.rel,
                is_async=is_async,
                decorators=decs,
            )
        )
        # classic bot handlers by name
        if node.name in ("start", "help", "status", "admin", "start_cmd", "help_cmd", "status_cmd"):
            cmd = node.name.replace("_cmd", "")
            self.commands.append(
                DetectedCommand(
                    name=cmd,
                    source_file=self.rel,
                    evidence=f"def {node.name}",
                    registration="def",
                )
            )
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> Any:
        fname = _base_name(node.func)
        # CommandHandler("start", ...)
        if fname == "CommandHandler" and node.args:
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                name = a0.value.lstrip("/").lower()
                if name and name.isidentifier():
                    self.commands.append(
                        DetectedCommand(
                            name=name,
                            source_file=self.rel,
                            evidence=f'CommandHandler("{name}")',
                            registration="CommandHandler",
                        )
                    )
                    self.handlers.append(
                        DetectedHandler(kind="command", name=name, source_file=self.rel)
                    )
                    self.is_tg = True
        if fname in ("CallbackQueryHandler", "MessageHandler", "ConversationHandler"):
            kind = {
                "CallbackQueryHandler": "callback",
                "MessageHandler": "message",
                "ConversationHandler": "conversation",
            }[fname]
            self.handlers.append(DetectedHandler(kind=kind, name=fname, source_file=self.rel))
            self.is_tg = True
        if fname == "BotCommand" and node.args:
            a0 = node.args[0]
            if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                name = a0.value.lstrip("/").lower()
                if name:
                    self.commands.append(
                        DetectedCommand(
                            name=name,
                            source_file=self.rel,
                            evidence=f'BotCommand("{name}")',
                            registration="BotCommand",
                        )
                    )
        # os.getenv("X") / getenv("X")
        if fname in ("getenv", "environ") or (
            isinstance(node.func, ast.Attribute) and node.func.attr == "getenv"
        ):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                self.env_vars.append(EnvVarInfo(name=node.args[0].value, source_file=self.rel))
        self.generic_visit(node)


def _analyze_python_file(path: Path, root: Path) -> _ModuleAnalyzer | None:
    tree = _parse_ast(path)
    if tree is None:
        return None
    rel = str(path.relative_to(root)).replace("\\", "/")
    an = _ModuleAnalyzer(rel)
    an.lines = len(_read(path).splitlines())
    an.visit(tree)
    return an


def _detect_layers(root: Path, py_files: list[Path]) -> list[LayerInfo]:
    counts: Counter[str] = Counter()
    for p in py_files:
        parts = p.relative_to(root).parts
        if len(parts) >= 2:
            # telegram_bot_engine/formal_engine/...
            if parts[0] == "telegram_bot_engine" and len(parts) >= 2:
                counts[parts[1]] += 1
            else:
                counts[parts[0]] += 1
        elif len(parts) == 1:
            counts["(root)"] += 1
    layers = []
    for name, cnt in counts.most_common(15):
        if name == "(root)":
            continue
        layers.append(
            LayerInfo(
                name=name,
                path=name if name != "telegram_bot_engine" else name,
                file_count=cnt,
                role=_LAYER_ROLES.get(name, ""),
            )
        )
    return layers


def _architecture(
    is_tg: bool,
    is_gen: bool,
    layers: list[LayerInfo],
    engines: list[str],
) -> tuple[str, str]:
    if is_gen:
        return (
            "generation_engine",
            "محرك توليد بوتات تليجرام متعدد الطبقات (فهم → تخطيط → توليد → تحقق).",
        )
    if is_tg:
        return "telegram_bot", "مشروع بوت تليجرام."
    if any(l.name in ("app", "handlers", "services") for l in layers):
        return "modular", "مشروع بايثون متعدد الطبقات."
    if engines:
        return "modular", "نظام محركات متخصصة."
    return "unknown", "هيكل عام."


def _confidence(
    *,
    py_count: int,
    is_tg: bool,
    is_gen: bool,
    commands: int,
    entries: int,
    classes: int,
    deps: int,
    layers: int,
) -> float:
    c = 0.2
    if py_count:
        c += 0.15
    if is_tg:
        c += 0.15
    if is_gen:
        c += 0.15
    if commands:
        c += 0.1
    if entries:
        c += 0.08
    if classes >= 5:
        c += 0.08
    if deps:
        c += 0.05
    if layers >= 3:
        c += 0.09
    return round(min(0.99, c), 3)


class RepoUnderstandingService:
    """Deep deterministic repository understanding."""

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

        # size ranking
        top_files: list[FileEntry] = []
        for p in sorted(files, key=lambda x: x.stat().st_size if x.exists() else 0, reverse=True)[:30]:
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
                if p.relative_to(root).parts
            }
        )[:25]

        languages: list[str] = []
        if py_files:
            languages.append("python")
        if any(p.suffix == ".js" for p in files):
            languages.append("javascript")
        if any(p.suffix == ".ts" for p in files):
            languages.append("typescript")

        deps = _parse_requirements(root)

        # AST pass (cap for speed on huge repos)
        analyzers: list[_ModuleAnalyzer] = []
        for p in py_files[:200]:
            an = _analyze_python_file(p, root)
            if an:
                analyzers.append(an)

        all_cmds: list[DetectedCommand] = []
        all_handlers: list[DetectedHandler] = []
        all_classes: list[ClassInfo] = []
        all_fns: list[FunctionInfo] = []
        all_env: list[EnvVarInfo] = []
        import_counter: Counter[str] = Counter()
        is_tg = False
        has_async = False
        has_typing = False
        total_lines = 0

        for an in analyzers:
            all_cmds.extend(an.commands)
            all_handlers.extend(an.handlers)
            all_classes.extend(an.classes)
            all_fns.extend(an.functions)
            all_env.extend(an.env_vars)
            import_counter.update(an.imports)
            is_tg = is_tg or an.is_tg
            has_async = has_async or an.has_async
            has_typing = has_typing or an.has_typing
            total_lines += an.lines

        # frameworks from deps + imports
        frameworks: list[str] = []
        blob = " ".join(deps).lower() + " " + " ".join(import_counter.keys()).lower()
        for needle, name in _FRAMEWORK_MAP.items():
            if needle in blob and name not in frameworks:
                frameworks.append(name)

        # dedupe commands — prefer CommandHandler registration
        cmd_map: dict[str, DetectedCommand] = {}
        rank = {"CommandHandler": 3, "BotCommand": 2, "def": 1, "decorator": 2, "": 0}
        for c in all_cmds:
            prev = cmd_map.get(c.name)
            if prev is None or rank.get(c.registration, 0) > rank.get(prev.registration, 0):
                cmd_map[c.name] = c
        # order start/help first
        def _ck(c: DetectedCommand) -> tuple:
            return (0 if c.name in ("start", "help") else 1, c.name)

        commands = sorted(cmd_map.values(), key=_ck)[:25]

        # handlers dedupe
        h_seen = set()
        handlers: list[DetectedHandler] = []
        for h in all_handlers:
            k = (h.kind, h.source_file, h.name)
            if k not in h_seen:
                h_seen.add(k)
                handlers.append(h)

        # entry points with score
        entries: list[EntryPoint] = []
        for rel, score in _ENTRY_NAMES.items():
            if (root / rel).exists():
                entries.append(EntryPoint(path=rel, reason="standard_name", score=score))
        for an in analyzers:
            if an.rel.startswith("tests/") or "test" in an.rel.lower():
                continue
            # has if __name__
            src = _read(root / an.rel, 80_000)
            if re.search(r'if\s+__name__\s*==\s*["\']__main__["\']', src):
                if not any(e.path == an.rel for e in entries):
                    score = 70
                    if "CommandHandler" in src or "Application" in src:
                        score = 92
                    entries.append(EntryPoint(path=an.rel, reason="__main__", score=score))
        entries = sorted(entries, key=lambda e: -e.score)[:8]

        # layers, engines, services, models
        layers = _detect_layers(root, py_files)
        engines = sorted({c.name for c in all_classes if c.kind == "engine" and c.name not in ("Engine", "BaseEngine", "FakeEngine", "NamingEngine")})[:30]
        services = sorted({c.name for c in all_classes if c.kind == "service"})[:20]
        data_models = sorted({c.name for c in all_classes if c.kind == "pydantic"})[:30]

        # generation engine signals
        is_gen = any(
            x in import_counter or (root / "telegram_bot_engine").exists()
            for x in ()
        )
        is_gen = (root / "telegram_bot_engine").exists() or any(
            "generate_bot" in f.name or f.name == "CodegenService" for f in all_classes + all_fns  # type: ignore
        )
        is_gen = (root / "telegram_bot_engine").exists() or any(
            getattr(x, "name", "") in ("CodegenService", "UnderstandingService", "PlanningService", "generate_bot")
            for x in list(all_classes) + list(all_fns)
        )

        # key classes: engines, services, pydantic, large method sets
        key_classes = sorted(
            all_classes,
            key=lambda c: (
                0 if c.kind in ("engine", "service") else 1 if c.kind == "pydantic" else 2,
                -len(c.methods),
                c.name,
            ),
        )[:25]

        key_functions = [
            f
            for f in all_fns
            if f.name in ("main", "generate_bot", "understand", "plan", "smart_clone", "understand_repo")
            or f.name.startswith("generate_")
        ][:20]

        # env vars dedupe
        env_map = {e.name: e for e in all_env if e.name and e.name.isupper()}
        env_vars = list(env_map.values())[:30]

        # modules sample (largest)
        modules_sample: list[ModuleInfo] = []
        for an in sorted(analyzers, key=lambda a: -a.lines)[:15]:
            modules_sample.append(
                ModuleInfo(
                    path=an.rel,
                    imports=sorted(set(an.imports))[:15],
                    classes=[c.name for c in an.classes][:10],
                    functions=[f.name for f in an.functions][:10],
                    lines=an.lines,
                )
            )

        style, arch_summary = _architecture(is_tg, is_gen, layers, engines)

        has_tests = any("tests" in str(p) or p.name.startswith("test_") for p in py_files)

        notes: list[str] = []
        if not py_files:
            notes.append("no_python_files")
        if is_tg and not commands:
            notes.append("telegram_signals_but_no_registered_commands")
        if not entries:
            notes.append("no_clear_entry_point")
        if is_gen:
            notes.append("project_is_generation_engine_not_simple_bot")

        conf = _confidence(
            py_count=len(py_files),
            is_tg=is_tg,
            is_gen=is_gen,
            commands=len(commands),
            entries=len(entries),
            classes=len(all_classes),
            deps=len(deps),
            layers=len(layers),
        )

        if is_gen:
            summary = (
                f"محرك توليد بوتات — {len(engines)} محرك، "
                f"{len(commands)} أوامر واجهة، {len(data_models)} نموذج بيانات."
            )
        elif is_tg:
            summary = f"بوت تليجرام — {len(commands)} أمر مسجّل، {len(handlers)} handler."
        else:
            summary = f"مشروع Python — {len(all_classes)} صنف، {len(py_files)} ملف."

        return RepoContract(
            root_path=str(root),
            repo_name=root.name,
            remote_url=remote_url or "",
            languages=languages,
            frameworks=frameworks,
            architecture_style=style,
            entry_points=entries,
            commands=commands,
            handlers=handlers[:40],
            dependencies=deps,
            layers=layers,
            key_classes=key_classes,
            key_functions=key_functions,
            modules_sample=modules_sample,
            env_vars=env_vars,
            data_models=data_models,
            services=services,
            engines=engines,
            file_count=len(files),
            python_file_count=len(py_files),
            total_lines=total_lines,
            top_files=top_files,
            top_dirs=dirs,
            is_telegram_bot=is_tg,
            is_generation_engine=is_gen,
            confidence=conf,
            summary=summary,
            architecture_summary=arch_summary,
            notes=notes,
            quality_signals={
                "has_tests": has_tests,
                "has_typing": has_typing,
                "has_async": has_async,
                "class_count": len(all_classes),
                "function_count": len(all_fns),
                "ast_modules_scanned": len(analyzers),
            },
            raw_stats={
                "top_imports": [n for n, _ in import_counter.most_common(15)],
                "handler_kinds": sorted({h.kind for h in handlers}),
            },
        )


def understand_repo(root_path: str | Path, remote_url: str = "") -> RepoContract:
    return RepoUnderstandingService().run(root_path, remote_url=remote_url)
