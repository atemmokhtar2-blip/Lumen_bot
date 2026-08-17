"""
Anti-Hallucination Gate — strong post-generation verification.

Goals:
  1. Never claim a feature exists unless code + handlers prove it.
  2. Detect stub / empty / placeholder handlers.
  3. Reject projects with syntax errors or missing core entry points.
  4. Produce an honest user-facing list of VERIFIED capabilities only.
  5. Block ready_for_token when hard errors are present.

This gate is deterministic (no LLM). It only inspects files + optional BotSpec.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


# Phrases that indicate a handler is a stub / placeholder (hallucination risk)
_STUB_MARKERS = (
    "not implemented",
    "todo",
    "pass  #",
    "raise notimplementederror",
    "coming soon",
    "قريباً",
    "غير متاح",
    "placeholder",
    "stub",
    "...",  # alone in body is weak; combined with short body below
)

# Fake marketing claims we never want in generated start/help text without code
_OVERCLAIM_PATTERNS = (
    r"ai[\s\-]?powered",
    r"chatgpt|gpt\-?4|openai",
    r"machine learning|deep learning",
    r"blockchain|nft|web3",
    r"دفع فوري|instant payment|stripe|paypal",  # only if no payment service code
)

_CORE_ENTRY_CANDIDATES = (
    "main.py",
    "bot.py",
    "app.py",
    "run.py",
    "app/main.py",
)


@dataclass
class Finding:
    severity: str  # error | warning | info
    code: str
    message_ar: str
    message_en: str = ""
    evidence: str = ""


@dataclass
class AntiHallucinationReport:
    ok: bool
    ready_for_token: bool
    errors: list[Finding] = field(default_factory=list)
    warnings: list[Finding] = field(default_factory=list)
    verified_commands: list[str] = field(default_factory=list)
    verified_handlers: list[str] = field(default_factory=list)
    stub_handlers: list[str] = field(default_factory=list)
    claimed_but_missing: list[str] = field(default_factory=list)
    files_checked: int = 0
    syntax_ok: bool = True
    structure_ok: bool = True
    fidelity_ok: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "ready_for_token": self.ready_for_token,
            "errors": [
                {"code": f.code, "ar": f.message_ar, "en": f.message_en, "evidence": f.evidence}
                for f in self.errors
            ],
            "warnings": [
                {"code": f.code, "ar": f.message_ar, "en": f.message_en}
                for f in self.warnings
            ],
            "verified_commands": list(self.verified_commands),
            "verified_handlers": list(self.verified_handlers),
            "stub_handlers": list(self.stub_handlers),
            "claimed_but_missing": list(self.claimed_but_missing),
            "files_checked": self.files_checked,
            "syntax_ok": self.syntax_ok,
            "structure_ok": self.structure_ok,
            "fidelity_ok": self.fidelity_ok,
            "metadata": dict(self.metadata),
        }

    def to_user_text(self, lang: str = "ar") -> str:
        """Honest summary for the Telegram user — verified facts only."""
        if lang.startswith("en"):
            return self._to_user_en()
        return self._to_user_ar()

    def _to_user_ar(self) -> str:
        lines: list[str] = []
        if self.ok and self.ready_for_token:
            lines.append("✅ *تم التحقق — لا توجد هلوسة هيكلية*")
        elif self.ok:
            lines.append("⚠️ *تم التوليد مع تحذيرات — راجع القائمة*")
        else:
            lines.append("❌ *فشل التحقق — المشروع غير جاهز للتشغيل*")

        lines.append("")
        lines.append("*ما تم التحقق منه فعلياً:*")
        if self.verified_commands:
            lines.append("• أوامر مسجّلة + لها handler حقيقي:")
            for c in self.verified_commands[:20]:
                lines.append(f"  – `/{c}`")
        else:
            lines.append("• لا أوامر مؤكدة بعد.")

        if self.stub_handlers:
            lines.append("")
            lines.append("*handlers فارغة / وهمية (تم رفض الادعاء بها):*")
            for s in self.stub_handlers[:12]:
                lines.append(f"  – `{s}`")

        if self.claimed_but_missing:
            lines.append("")
            lines.append("*مذكور في المواصفات لكن غير موجود في الكود:*")
            for c in self.claimed_but_missing[:12]:
                lines.append(f"  – `{c}`")

        if self.errors:
            lines.append("")
            lines.append("*أخطاء تمنع التسليم:*")
            for e in self.errors[:15]:
                lines.append(f"  🔴 {e.message_ar}")

        if self.warnings and not self.errors:
            lines.append("")
            lines.append("*تحذيرات:*")
            for w in self.warnings[:10]:
                lines.append(f"  🟡 {w.message_ar}")

        lines.append("")
        lines.append(
            "_لا ندّعي وجود ميزة إلا بعد التحقق من الكود الفعلي._"
        )
        return "\n".join(lines)

    def _to_user_en(self) -> str:
        lines: list[str] = []
        if self.ok and self.ready_for_token:
            lines.append("✅ *Verified — no structural hallucination*")
        elif self.ok:
            lines.append("⚠️ *Generated with warnings*")
        else:
            lines.append("❌ *Verification failed — not ready to run*")
        lines.append("")
        lines.append("*Actually verified:*")
        if self.verified_commands:
            for c in self.verified_commands[:20]:
                lines.append(f"  – `/{c}`")
        else:
            lines.append("  – no confirmed commands")
        if self.errors:
            lines.append("")
            lines.append("*Blocking errors:*")
            for e in self.errors[:15]:
                lines.append(f"  🔴 {e.message_en or e.message_ar}")
        return "\n".join(lines)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _find_entry(root: Path) -> Path | None:
    for rel in _CORE_ENTRY_CANDIDATES:
        p = root / rel
        if p.is_file():
            return p
    for name in ("main.py", "bot.py"):
        for p in root.rglob(name):
            if any(x in p.parts for x in (".venv", "venv", "__pycache__")):
                continue
            return p
    return None


def _iter_py(root: Path) -> Iterable[Path]:
    for p in root.rglob("*.py"):
        if any(x in p.parts for x in (".venv", "venv", "__pycache__", ".git")):
            continue
        yield p


def _handler_body_is_stub(body: str) -> bool:
    """Heuristic: short body with no real side effects = stub."""
    cleaned = re.sub(r"#.*", "", body)
    cleaned = re.sub(r'""".*?"""', "", cleaned, flags=re.S)
    cleaned = re.sub(r"'''.*?'''", "", cleaned, flags=re.S)
    stripped = cleaned.strip().lower()
    if not stripped or stripped in ("pass", "..."):
        return True
    for m in _STUB_MARKERS:
        if m in stripped:
            # allow "todo" only if body is very short
            if m in ("todo", "...") and len(stripped) > 400:
                continue
            return True
    # Real work signals
    real_signals = (
        "reply_text",
        "reply_photo",
        "reply_document",
        "edit_message",
        "send_message",
        "answer_callback",
        "update.message",
        "context.bot",
        "await ",
        "sqlite",
        "json.",
        "open(",
        "path(",
        "session",
        "db.",
        "service.",
        "run_tool",
        "create_record",
        "list_records",
        "_start_flow",
        "flows.get",
    )
    if any(s in stripped for s in real_signals):
        return False
    # No real signals and body short → stub
    return len(stripped) < 120


def _extract_async_handlers(src: str) -> dict[str, str]:
    """Map function name → approximate body text."""
    out: dict[str, str] = {}
    for m in re.finditer(
        r"async def ([a-zA-Z_][a-zA-Z0-9_]*)\s*\([^)]*\)\s*(?:->[^:]+)?:\s*\n",
        src,
    ):
        name = m.group(1)
        rest = src[m.end() :]
        end = re.search(r"\n(?:async def |def |class )", rest)
        body = rest[: end.start()] if end else rest[:3000]
        out[name] = body
    return out


def _extract_command_handlers(src: str) -> list[str]:
    return re.findall(
        r"CommandHandler\(\s*['\"]([a-zA-Z][a-zA-Z0-9_]*)['\"]",
        src,
    )


def _extract_command_bindings(src: str) -> list[tuple[str, str]]:
    """Read CommandHandler(command, handler) bindings from Python AST."""
    bindings: list[tuple[str, str]] = []
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return bindings
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.id if isinstance(fn, ast.Name) else fn.attr if isinstance(fn, ast.Attribute) else ""
        if name != "CommandHandler" or len(node.args) < 2:
            continue
        command, handler = node.args[0], node.args[1]
        if isinstance(command, ast.Constant) and isinstance(command.value, str):
            if isinstance(handler, ast.Name):
                bindings.append((command.value, handler.id))
    return bindings


def _local_import_findings(root: Path, files: list[Path]) -> list[Finding]:
    """Validate local imports statically without importing or executing generated code."""
    findings: list[Finding] = []
    known_top = {p.name for p in root.iterdir() if p.is_dir()}
    for py in files:
        try:
            tree = ast.parse(_read(py), filename=str(py))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or node.level != 0 or not node.module:
                continue
            parts = node.module.split(".")
            if parts[0] not in known_top:
                continue
            mod_file = root.joinpath(*parts).with_suffix(".py")
            mod_init = root.joinpath(*parts, "__init__.py")
            if not mod_file.is_file() and not mod_init.is_file():
                findings.append(Finding("error", "local_import_module_missing", f"الاستيراد المحلي `{node.module}` غير موجود", f"Local import module missing: {node.module}"))
                continue
            target = mod_file if mod_file.is_file() else mod_init
            try:
                target_tree = ast.parse(_read(target), filename=str(target))
                defined = {n.name for n in target_tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))}
                for n in target_tree.body:
                    if isinstance(n, ast.Assign):
                        defined.update(t.id for t in n.targets if isinstance(t, ast.Name))
                    elif isinstance(n, ast.AnnAssign) and isinstance(n.target, ast.Name):
                        defined.add(n.target.id)
            except SyntaxError:
                continue
            for alias in node.names:
                if alias.name == "*" or alias.name in defined:
                    continue
                submodule = target.parent / alias.name
                if submodule.with_suffix(".py").is_file() or (submodule / "__init__.py").is_file():
                    continue
                findings.append(Finding("error", "local_import_symbol_missing", f"الاسم `{alias.name}` غير موجود في `{node.module}`", f"Imported symbol {alias.name} missing from {node.module}"))
    return findings


def _runtime_import_findings(root: Path) -> list[Finding]:
    """Import generated local modules in an isolated, network-free subprocess."""
    modules = []
    for rel in ("app/handlers.py", "app/flow_engine.py"):
        if (root / rel).is_file():
            modules.append(rel[:-3].replace("/", "."))
    services = root / "app" / "services"
    if services.is_dir():
        modules.extend(
            f"app.services.{p.stem}"
            for p in services.glob("*.py")
            if p.name != "__init__.py"
        )
    if not modules:
        return []
    # Smoke-import generated modules. If python-telegram-bot is not installed in
    # the host env, inject a minimal stub so we still catch *local* import errors.
    stub_dir = root / ".ah_import_stub"
    try:
        import telegram  # noqa: F401
        stub_needed = False
    except Exception:
        stub_needed = True
    if stub_needed:
        stub_dir.mkdir(parents=True, exist_ok=True)
        (stub_dir / "telegram").mkdir(exist_ok=True)
        (stub_dir / "telegram" / "__init__.py").write_text(
            "\n".join([
                "class Update: pass",
                "class Message: pass",
                "class User: pass",
                "class Chat: pass",
                "class CallbackQuery: pass",
                "class InlineKeyboardButton:",
                "    def __init__(self, *a, **k): pass",
                "class InlineKeyboardMarkup:",
                "    def __init__(self, *a, **k): pass",
                "class ReplyKeyboardMarkup:",
                "    def __init__(self, *a, **k): pass",
                "class KeyboardButton:",
                "    def __init__(self, *a, **k): pass",
                "class BotCommand:",
                "    def __init__(self, *a, **k): pass",
                "class ChatPermissions:",
                "    def __init__(self, **kwargs): pass",
                "class LabeledPrice:",
                "    def __init__(self, *a, **k): pass",
                "class SuccessfulPayment: pass",
                "class PreCheckoutQuery: pass",
            ]) + "\n",
            encoding="utf-8",
        )
        (stub_dir / "telegram" / "ext.py").write_text(
            "\n".join([
                "class ContextTypes:",
                "    DEFAULT_TYPE = object",
                "class Application: pass",
                "class ApplicationBuilder:",
                "    def token(self, *a, **k): return self",
                "    def post_init(self, *a, **k): return self",
                "    def concurrent_updates(self, *a, **k): return self",
                "    def build(self): return Application()",
                "class CommandHandler:",
                "    def __init__(self, *a, **k): pass",
                "class MessageHandler:",
                "    def __init__(self, *a, **k): pass",
                "class CallbackQueryHandler:",
                "    def __init__(self, *a, **k): pass",
                "class ChatMemberHandler:",
                "    def __init__(self, *a, **k): pass",
                "    CHAT_MEMBER = 1",
                "class PreCheckoutQueryHandler:",
                "    def __init__(self, *a, **k): pass",
                "class filters:",
                "    TEXT = type('F', (), {'__and__': lambda self, o: self, '__invert__': lambda self: self})()",
                "    COMMAND = type('F', (), {})()",
                "    PHOTO = type('F', (), {})()",
                "    VOICE = type('F', (), {'__or__': lambda self, o: self})()",
                "    AUDIO = type('F', (), {})()",
                "    SUCCESSFUL_PAYMENT = type('F', (), {})()",
            ]) + "\n",
            encoding="utf-8",
        )
    code = "import importlib\n" + "\n".join(
        f"importlib.import_module({name!r})" for name in dict.fromkeys(modules)
    )
    from telegram_bot_engine.services.secure_exec import clean_child_environ
    pp = str(root)
    if stub_needed:
        pp = str(stub_dir) + ":" + pp
    env = clean_child_environ({"PYTHONPATH": pp})
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(root),
            env=env,
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [Finding("error", "runtime_import_timeout", "انتهى وقت فحص استيراد ملفات البوت", "Generated module import smoke test timed out")]
    if proc.returncode:
        evidence = (proc.stderr or proc.stdout or "").strip()[-1200:]
        return [Finding("error", "runtime_import_error", "فشل استيراد أحد ملفات البوت المولد قبل التسليم", "Generated module import smoke test failed", evidence)]
    return []


def _load_spec_features(root: Path) -> list[str]:
    """Features claimed by written artifacts (spec / contract / manifest)."""
    claimed: list[str] = []
    for name in (
        "bot_spec.json",
        "program_contract.json",
        "spec.json",
        "manifest.json",
    ):
        p = root / name
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(data, dict):
            feats = data.get("features") or data.get("capabilities") or []
            if isinstance(feats, list):
                for f in feats:
                    if isinstance(f, str):
                        claimed.append(f)
                    elif isinstance(f, dict):
                        key = f.get("feature") or f.get("id") or f.get("name")
                        if key:
                            claimed.append(str(key))
            cmds = data.get("commands") or []
            if isinstance(cmds, list):
                for c in cmds:
                    if isinstance(c, str):
                        claimed.append(c)
                    elif isinstance(c, dict) and c.get("name"):
                        claimed.append(str(c["name"]))
    return claimed


def run_anti_hallucination_gate(
    project_dir: str | Path,
    *,
    claimed_features: list[str] | None = None,
    user_request: str = "",
) -> AntiHallucinationReport:
    """Run full anti-hallucination checks on a generated project directory."""
    root = Path(project_dir)
    rep = AntiHallucinationReport(ok=True, ready_for_token=False)

    # Reject clearly non-bot user requests even if a template was emitted
    try:
        from ...spec_core.arabic_intent_engine import is_clearly_non_bot, detect_bot_request_arabic
        if user_request and is_clearly_non_bot(user_request):
            rep.ok = False
            rep.ready_for_token = False
            rep.fidelity_ok = False
            rep.errors.append(
                Finding(
                    "error",
                    "invalid_request",
                    "الطلب ليس طلب بوت (مثلاً قصة/مقال). لن يُسلَّم كمشروع جاهز.",
                    "Request is not a bot specification; refusing ready_for_token.",
                )
            )
            rep.metadata["user_request_preview"] = (user_request or "")[:200]
            return rep
        domain, conf = detect_bot_request_arabic(user_request or "")
        if user_request and conf < 0.15 and domain is None:
            # soft: continue structural checks but do not claim ready
            rep.warnings.append(
                Finding(
                    "warning",
                    "low_intent_confidence",
                    "ثقة منخفضة في أن الطلب يصف بوت تيليجرام.",
                    "Low confidence that the request describes a Telegram bot.",
                )
            )
    except Exception:
        pass

    if not root.is_dir():
        rep.ok = False
        rep.structure_ok = False
        rep.errors.append(
            Finding(
                "error",
                "project_missing",
                "مجلد المشروع غير موجود",
                "Project directory missing",
            )
        )
        return rep

    # ── 1. Syntax of every Python file ──────────────────────────────────
    files = list(_iter_py(root))
    rep.files_checked = len(files)
    if not files:
        rep.ok = False
        rep.structure_ok = False
        rep.errors.append(
            Finding(
                "error",
                "no_python_files",
                "لا توجد ملفات Python في المشروع",
                "No Python files in project",
            )
        )
        return rep

    for py in files:
        src = _read(py)
        try:
            ast.parse(src, filename=str(py))
        except SyntaxError as e:
            rep.syntax_ok = False
            rep.ok = False
            rep.errors.append(
                Finding(
                    "error",
                    "syntax_error",
                    f"خطأ نحوي في `{py.relative_to(root)}` سطر {e.lineno}",
                    f"Syntax error in {py.relative_to(root)}:{e.lineno}",
                    evidence=str(e.msg or ""),
                )
            )

    for finding in _local_import_findings(root, files):
        rep.errors.append(finding)
    for finding in _runtime_import_findings(root):
        rep.errors.append(finding)
    if any(f.code.startswith("local_import_") or f.code.startswith("runtime_import_") for f in rep.errors):
        rep.ok = False
        rep.structure_ok = False

    # Reject symlinks that escape the generated project directory.
    for py in files:
        try:
            py.resolve().relative_to(root.resolve())
        except ValueError:
            rep.ok = False
            rep.structure_ok = False
            rep.errors.append(Finding("error", "path_escape", f"ملف خارج مجلد المشروع: `{py}`", f"Project file escapes root: {py}"))

    # ── 2. Entry point + Application ────────────────────────────────────
    entry = _find_entry(root)
    if entry is None:
        rep.structure_ok = False
        rep.ok = False
        rep.errors.append(
            Finding(
                "error",
                "no_entry_point",
                "لا يوجد main.py / bot.py كنقطة دخول",
                "No main.py / bot.py entry point",
            )
        )
        main_src = ""
    else:
        main_src = _read(entry)
        if "Application" not in main_src and "ApplicationBuilder" not in main_src:
            # Still allow very simple bots that use Updater only with warning
            if "Updater(" in main_src:
                rep.warnings.append(
                    Finding(
                        "warning",
                        "legacy_ptb",
                        "يستخدم python-telegram-bot بأسلوب قديم (v13)",
                        "Uses legacy PTB v13 style",
                    )
                )
            else:
                rep.structure_ok = False
                rep.ok = False
                rep.errors.append(
                    Finding(
                        "error",
                        "no_application",
                        "الملف الرئيسي لا يبني Application لتيليجرام",
                        "Entry file does not build a Telegram Application",
                    )
                )

    # ── 3. Handlers: real vs stub ───────────────────────────────────────
    all_handler_src = main_src
    for cand in (
        root / "app" / "handlers.py",
        root / "handlers.py",
        root / "app" / "handlers" / "__init__.py",
    ):
        if cand.is_file():
            all_handler_src += "\n" + _read(cand)
    # Also gather handlers package
    handlers_dir = root / "app" / "handlers"
    if handlers_dir.is_dir():
        for p in handlers_dir.glob("*.py"):
            all_handler_src += "\n" + _read(p)

    handlers = _extract_async_handlers(all_handler_src)
    combined_src = main_src + "\n" + all_handler_src
    bindings = _extract_command_bindings(combined_src)
    binding_map = {cmd: handler for cmd, handler in bindings}
    commands = [cmd for cmd, _ in bindings] or _extract_command_handlers(combined_src)
    # de-dupe preserve order
    seen_cmd: set[str] = set()
    commands = [c for c in commands if not (c in seen_cmd or seen_cmd.add(c))]

    for name, body in handlers.items():
        if name.startswith("_"):
            continue
        if _handler_body_is_stub(body):
            rep.stub_handlers.append(name)
            rep.warnings.append(
                Finding(
                    "warning",
                    "stub_handler",
                    f"الدالة `{name}` تبدو فارغة/وهمية ولن تُعرض كميزة",
                    f"Handler `{name}` looks like a stub",
                    evidence=body[:120].strip(),
                )
            )
        else:
            rep.verified_handlers.append(name)

    # Commands must have a non-stub handler
    for cmd in commands:
        # common patterns: cmd_handler, handle_cmd, cmd
        candidates = (
            f"{cmd}_handler",
            f"handle_{cmd}",
            cmd,
            f"{cmd}_cmd",
            f"cmd_{cmd}",
        )
        matched = binding_map.get(cmd)
        if matched not in handlers:
            matched = None
        if matched is None:
            for cand in candidates:
                if cand in handlers:
                    matched = cand
                    break
        if matched is None:
            # soft: CommandHandler may point to a shared function
            # only error if we have zero evidence
            rep.warnings.append(
                Finding(
                    "warning",
                    "command_handler_name_unclear",
                    f"الأمر `/{cmd}` مسجّل لكن اسم الـ handler غير واضح",
                    f"Command /{cmd} registered but handler name unclear",
                )
            )
            rep.claimed_but_missing.append(cmd)
            rep.errors.append(Finding("error", "missing_handler", f"الأمر `/{cmd}` مسجّل بدون handler قابل للتتبع", f"Command /{cmd} has no traceable handler"))
            rep.ok = False
            rep.fidelity_ok = False
            continue

        if matched in rep.stub_handlers:
            rep.claimed_but_missing.append(cmd)
            rep.errors.append(
                Finding(
                    "error",
                    "command_is_stub",
                    f"الأمر `/{cmd}` موجود شكلياً لكن الـ handler وهمي",
                    f"Command /{cmd} maps to a stub handler",
                )
            )
            rep.ok = False
            rep.fidelity_ok = False
        else:
            rep.verified_commands.append(cmd)

    # Must have at least /start verified or a message handler
    has_start = "start" in rep.verified_commands or any(
        n in rep.verified_handlers for n in ("start", "start_handler", "handle_start")
    )
    has_msg = any(
        n in rep.verified_handlers
        for n in ("message_handler", "handle_message", "on_message", "echo")
    )
    if not has_start and not has_msg:
        rep.ok = False
        rep.structure_ok = False
        rep.errors.append(
            Finding(
                "error",
                "no_start_or_message",
                "لا يوجد /start حقيقي ولا message handler — البوت لن يرد",
                "No real /start or message handler — bot would not respond",
            )
        )

    # ── 4. Claimed features vs code ─────────────────────────────────────
    claimed = list(claimed_features or [])
    claimed.extend(_load_spec_features(root))
    # normalize
    claimed_norm = []
    for c in claimed:
        c = str(c).strip().lstrip("/")
        if c and c not in claimed_norm:
            claimed_norm.append(c)

    for feat in claimed_norm:
        # if feature looks like a command name, require verification
        if re.match(r"^[a-z][a-z0-9_]{1,32}$", feat):
            if feat not in rep.verified_commands and feat not in rep.verified_handlers:
                # not automatically error — preset features may map to services
                if feat not in rep.claimed_but_missing:
                    rep.warnings.append(
                        Finding(
                            "warning",
                            "claimed_unverified",
                            f"الميزة `{feat}` مذكورة في المواصفات ولم يُؤكد وجودها كأمر/handler",
                            f"Feature `{feat}` claimed but not verified as command/handler",
                        )
                    )

    # ── 5. Over-claim scan in start/help text (marketing hallucination) ─
    scan_text = (main_src + "\n" + all_handler_src).lower()
    # payment claim without payment-ish code
    if re.search(r"stripe|paypal|دفع إلكتروني|بطاقة ائتمان", scan_text):
        if not re.search(r"stripe|paypal|payment_intent|checkout", scan_text):
            # weak text-only claim
            pass
    for pat in (r"chatgpt", r"gpt-4", r"openai api", r"powered by ai"):
        if re.search(pat, scan_text) and "openai" not in (_read(root / "requirements.txt")).lower():
            rep.warnings.append(
                Finding(
                    "warning",
                    "overclaim_ai",
                    "النص يدّعي قدرات AI دون مكتبات AI في requirements",
                    "Text claims AI capabilities without AI libs in requirements",
                )
            )
            break

    # ── 6. requirements sanity ──────────────────────────────────────────
    req = root / "requirements.txt"
    if not req.is_file():
        rep.ok = False
        rep.errors.append(
            Finding(
                "error",
                "no_requirements",
                "ملف requirements.txt مفقود",
                "requirements.txt missing",
            )
        )
    else:
        req_t = _read(req).lower()
        if "python-telegram-bot" not in req_t and "aiogram" not in req_t and "telebot" not in req_t:
            rep.ok = False
            rep.errors.append(
                Finding(
                    "error",
                    "no_telegram_lib",
                    "requirements لا تتضمن مكتبة تيليجرام",
                    "requirements missing a Telegram library",
                )
            )

    # ── 7. Optional: reuse gen_verify if available ───────────────────────
    try:
        from telegram_bot_engine.services.gen_verify import verify_generated_project

        gv = verify_generated_project(root)
        for e in gv.errors:
            if e not in {f.code for f in rep.errors}:
                # map gen_verify codes
                if e in ("handlers_py_missing", "main_py_missing"):
                    # may be alternate layout — only warn if we already found entry
                    if entry is None:
                        rep.ok = False
                        rep.errors.append(
                            Finding("error", e, f"تحقق إضافي: {e}", e)
                        )
                elif e.startswith("syntax:"):
                    rep.ok = False
                    rep.syntax_ok = False
                    rep.errors.append(
                        Finding("error", "syntax_error", f"تحقق إضافي: {e}", e)
                    )
                elif e.startswith("missing_handler:"):
                    cmd = e.split(":", 1)[-1]
                    if cmd not in rep.claimed_but_missing:
                        rep.claimed_but_missing.append(cmd)
                    rep.ok = False
                    rep.fidelity_ok = False
                    rep.errors.append(
                        Finding(
                            "error",
                            "missing_handler",
                            f"أمر مسجّل بدون handler: /{cmd}",
                            f"Registered command without handler: /{cmd}",
                        )
                    )
        for s in gv.stub_handlers:
            if s not in rep.stub_handlers:
                rep.stub_handlers.append(s)
    except Exception:
        pass

    # ── 8. Final verdict ────────────────────────────────────────────────
    # ready only if ok and we have at least one verified interaction path
    rep.ready_for_token = bool(
        rep.ok
        and rep.syntax_ok
        and rep.structure_ok
        and (rep.verified_commands or rep.verified_handlers)
        and not any(f.code == "command_is_stub" for f in rep.errors)
    )

    # If there are stub-only commands that were errors, already ok=False
    # Soft: many stubs but core works → ok may stay True with warnings
    if rep.errors:
        rep.ok = False
        rep.ready_for_token = False

    rep.metadata = {
        "entry": str(entry.relative_to(root)) if entry else None,
        "commands_registered": commands,
        "command_bindings": bindings,
        "user_request_preview": (user_request or "")[:200],
        "claimed_features": claimed_norm[:40],
    }
    return rep


def verified_capabilities_summary(report: AntiHallucinationReport, lang: str = "ar") -> str:
    """Short list of only verified capabilities (for captions / status)."""
    return report.to_user_text(lang=lang)


__all__ = [
    "Finding",
    "AntiHallucinationReport",
    "run_anti_hallucination_gate",
    "verified_capabilities_summary",
]
