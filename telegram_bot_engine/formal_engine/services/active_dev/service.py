"""
ActiveDevEngine — world-class foundation for developing an *existing* repo.

Pipeline (deterministic, no LLM):
  1) Long natural language → FormalBotSpec (existing deep extractor, 3000+ chars)
  2) Diff against RepoContract (commands, integrations, gaps)
  3) Apply safe code changes via AST-checked writes
  4) Sync requirements from integrations/features
  5) Rescan → updated RepoContract
  6) Honest report: applied / skipped / needs_manual

This replaces the weak keyword-only DevPlan path for real development turns.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...schemas.formal_spec import FormalBotSpec
from ...schemas.repo_contract import RepoContract
from ...understanding.requirement_extractor import extract_formal_spec
from ..repo_understanding import understand_repo


@dataclass
class AppliedChange:
    kind: str
    target: str
    detail: str
    ok: bool = True


@dataclass
class ActiveDevReport:
    ok: bool
    message: str
    spec_name: str = ""
    applied: list[AppliedChange] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    needs_manual: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    contract: RepoContract | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_user_text(self) -> str:
        icon = "✅" if self.ok else "⚠️"
        lines = [
            f"{icon} *تطوير المستودع النشط (محرك قوي)*",
            f"• المواصفة: {self.spec_name or '—'}",
        ]
        if self.applied:
            lines.append(f"• نُفّذ ({len(self.applied)}):")
            for a in self.applied[:20]:
                mark = "✓" if a.ok else "✗"
                lines.append(f"  {mark} `{a.kind}` → `{a.target}` — {a.detail[:120]}")
        if self.skipped:
            lines.append("• تُخطّي:")
            for s in self.skipped[:12]:
                lines.append(f"  • {s}")
        if self.needs_manual:
            lines.append("• يحتاج تنفيذ يدوي / برو لاحقاً:")
            for s in self.needs_manual[:12]:
                lines.append(f"  • {s}")
        if self.changed_files:
            lines.append("• ملفات تغيّرت: " + ", ".join(f"`{f}`" for f in self.changed_files[:15]))
        if self.contract and self.contract.intelligence:
            lines.append(
                f"• جاهزية بعد التطوير: {self.contract.intelligence.host_readiness:.0%}"
            )
        return "\n".join(lines)


# Integration / feature → PyPI packages (deterministic)
_FEATURE_PACKAGES: dict[str, list[str]] = {
    "payments": ["httpx"],
    "payment": ["httpx"],
    "stripe": ["stripe"],
    "openai": ["openai"],
    "gemini": ["google-generativeai"],
    "google-generativeai": ["google-generativeai"],
    "ai": ["httpx"],
    "redis": ["redis"],
    "postgres": ["asyncpg"],
    "postgresql": ["asyncpg"],
    "sqlite": [],
    "sqlalchemy": ["SQLAlchemy"],
    "fastapi": ["fastapi", "uvicorn"],
    "requests": ["requests"],
    "aiohttp": ["aiohttp"],
    "dotenv": ["python-dotenv"],
    "pydantic": ["pydantic"],
}


def _norm_cmd(name: str) -> str:
    n = (name or "").lstrip("/").strip().lower()
    n = re.sub(r"[^a-z0-9_]", "", n)
    return n[:32]


def _existing_commands(contract: RepoContract) -> set[str]:
    return {c.name.lower() for c in (contract.commands or [])}


def _primary_fw(contract: RepoContract) -> str:
    fws = [f.lower() for f in (contract.frameworks or [])]
    if any("aiogram" in f for f in fws):
        return "aiogram"
    if any("telebot" in f or "pytelegrambotapi" in f for f in fws):
        return "telebot"
    return "ptb"


def _find_entry(root: Path, contract: RepoContract) -> Path | None:
    for e in contract.entry_points or []:
        p = root / e.path
        if p.is_file() and p.suffix == ".py":
            return p
    for name in ("main.py", "bot.py", "app.py", "run.py"):
        p = root / name
        if p.is_file():
            return p
    return None


def _syntax_check(src: str, filename: str = "<code>") -> tuple[bool, str]:
    try:
        ast.parse(src, filename=filename)
        return True, ""
    except SyntaxError as e:
        return False, f"{e.msg} line {e.lineno}"


def _safe_write(path: Path, content: str) -> tuple[bool, str]:
    ok, err = _syntax_check(content, str(path))
    if not ok:
        return False, err
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True, ""


def _packages_from_spec(spec: FormalBotSpec, text: str) -> list[str]:
    pkgs: list[str] = []
    blob = (text or "").lower()
    tags = [t.lower() for t in (spec.feature_tags or [])]
    integrations = [i.lower() for i in (spec.integrations or [])]
    services = [s.lower() for s in (spec.services or [])]
    keys = tags + integrations + services
    if getattr(spec, "requires_payments", False):
        keys.append("payments")
    for k, plist in _FEATURE_PACKAGES.items():
        if k in blob or any(k in x for x in keys):
            for p in plist:
                if p not in pkgs:
                    pkgs.append(p)
    # explicit package names in text
    for m in re.finditer(
        r"(?:pip install|package|مكتبة|حزمة)\s+([a-zA-Z][a-zA-Z0-9_-]{1,40})",
        text or "",
        re.I,
    ):
        p = m.group(1)
        if p not in pkgs:
            pkgs.append(p)
    return pkgs


def _ensure_requirements(root: Path, packages: list[str]) -> list[str]:
    if not packages:
        return []
    req = root / "requirements.txt"
    existing = req.read_text(encoding="utf-8", errors="ignore") if req.exists() else ""
    present = {
        re.split(r"[<>=!~;\[]", ln)[0].strip().lower().replace("_", "-")
        for ln in existing.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    }
    added: list[str] = []
    block: list[str] = []
    for pkg in packages:
        key = pkg.lower().replace("_", "-")
        if key in present:
            continue
        block.append(pkg)
        added.append(pkg)
        present.add(key)
    if not added:
        return []
    if existing and not existing.endswith("\n"):
        existing += "\n"
    if "# active-dev-engine" not in existing:
        existing += "\n# active-dev-engine\n"
    existing += "\n".join(block) + "\n"
    req.write_text(existing, encoding="utf-8")
    return added


def _ptb_handler_block(cmd: str, description: str) -> str:
    func = f"{cmd}_cmd"
    desc = (description or cmd).replace('"', "'")[:120]
    return f'''

async def {func}(update, context):
    """Auto-generated by ActiveDevEngine: /{cmd} — {desc}"""
    await update.message.reply_text("{desc}")
'''


def _ptb_register_line(var: str, cmd: str) -> str:
    return f'{var}.add_handler(CommandHandler("{cmd}", {cmd}_cmd))\n'


def _inject_ptb_command(entry: Path, cmd: str, description: str) -> tuple[str, str]:
    """Insert handler + CommandHandler registration with robust detection."""
    src = entry.read_text(encoding="utf-8")
    if f'CommandHandler("{cmd}"' in src or f"CommandHandler('{cmd}'" in src:
        return "exists", src
    if f"async def {cmd}_cmd" in src or f"def {cmd}_cmd" in src:
        # function exists but maybe not registered
        pass
    else:
        block = _ptb_handler_block(cmd, description)
        if "if __name__" in src:
            src = src.replace("if __name__", block + "\nif __name__", 1)
        else:
            src = src.rstrip() + "\n" + block

    # ensure import CommandHandler
    if "CommandHandler" not in src:
        if "from telegram.ext import" in src:
            src = re.sub(
                r"from telegram\.ext import ([^\n]+)",
                lambda m: m.group(0)
                if "CommandHandler" in m.group(1)
                else f"from telegram.ext import CommandHandler, {m.group(1)}",
                src,
                count=1,
            )
        else:
            src = "from telegram.ext import CommandHandler\n" + src

    var = "application"
    if re.search(r"\bapp\s*=\s*Application", src):
        var = "app"
    elif re.search(r"\bapplication\s*=", src):
        var = "application"
    elif "ApplicationBuilder" in src or "Application.builder" in src:
        var = "application"

    reg = _ptb_register_line(var, cmd)
    if f'CommandHandler("{cmd}"' in src:
        return "exists", src

    lines = src.splitlines(keepends=True)
    insert_at = -1
    for i, line in enumerate(lines):
        if "add_handler" in line and "CommandHandler" in line:
            insert_at = i
    if insert_at >= 0:
        lines.insert(insert_at + 1, "    " + reg.lstrip() if lines[insert_at].startswith(" ") else reg)
        src = "".join(lines)
    else:
        # try before run_polling / run
        m = re.search(r"^(\s*)(.*\.(?:run_polling|run)\()", src, re.M)
        if m:
            indent = m.group(1) or "    "
            src = src[: m.start()] + f"{indent}{reg}" + src[m.start() :]
        else:
            src = src.rstrip() + "\n" + reg

    return "ok", src


def _aiogram_inject(entry: Path, cmd: str, description: str) -> tuple[str, str]:
    src = entry.read_text(encoding="utf-8")
    if f'Command("{cmd}")' in src or f"Command('{cmd}')" in src:
        return "exists", src
    desc = (description or cmd).replace('"', "'")[:120]
    block = f'''

@router.message(Command("{cmd}"))
async def {cmd}_handler(message: Message):
    """ActiveDevEngine: /{cmd}"""
    await message.answer("{desc}")
'''
    if "Command" not in src and "from aiogram" in src:
        if "from aiogram.filters import" in src:
            src = re.sub(
                r"from aiogram\.filters import ([^\n]+)",
                lambda m: m.group(0)
                if "Command" in m.group(1)
                else f"from aiogram.filters import Command, {m.group(1)}",
                src,
                count=1,
            )
        else:
            src = "from aiogram.filters import Command\n" + src
    if "async def main" in src:
        src = src.replace("async def main", block + "\n\nasync def main", 1)
    else:
        src = src.rstrip() + "\n" + block
    return "ok", src


def _telebot_inject(entry: Path, cmd: str, description: str) -> tuple[str, str]:
    src = entry.read_text(encoding="utf-8")
    if f"commands=['{cmd}']" in src or f'commands=["{cmd}"]' in src:
        return "exists", src
    desc = (description or cmd).replace('"', "'")[:120]
    block = f'''

@bot.message_handler(commands=["{cmd}"])
def {cmd}_handler(message):
    bot.reply_to(message, "{desc}")
'''
    src = src.rstrip() + "\n" + block
    return "ok", src


def _write_commands_module(
    root: Path, fw: str, new_cmds: list[tuple[str, str]]
) -> tuple[Path | None, str]:
    """Optional satellite module for many new commands (cleaner than bloating main)."""
    if len(new_cmds) < 3 or fw != "ptb":
        return None, ""
    path = root / "active_dev_commands.py"
    lines = [
        '"""Commands generated by ActiveDevEngine — do not edit by hand unless needed."""',
        "from __future__ import annotations",
        "",
        "from telegram import Update",
        "from telegram.ext import ContextTypes, CommandHandler",
        "",
    ]
    regs = []
    for cmd, desc in new_cmds:
        d = (desc or cmd).replace('"', "'")[:120]
        lines.append(f"async def {cmd}_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:")
        lines.append(f'    await update.message.reply_text("{d}")')
        lines.append("")
        regs.append(f'    app.add_handler(CommandHandler("{cmd}", {cmd}_cmd))')
    lines.append("")
    lines.append("def register_active_dev_commands(app) -> None:")
    lines.append('    """Register all ActiveDevEngine commands on an Application/app."""')
    lines.extend(regs)
    lines.append("")
    content = "\n".join(lines)
    ok, err = _safe_write(path, content)
    if not ok:
        return None, err
    return path, ""


def _wire_register_module(entry: Path, module_name: str = "active_dev_commands") -> tuple[str, str]:
    src = entry.read_text(encoding="utf-8")
    if f"register_active_dev_commands" in src:
        return "exists", src
    import_line = f"from {module_name} import register_active_dev_commands\n"
    if f"import register_active_dev_commands" not in src and f"from {module_name}" not in src:
        src = import_line + src
    call = "    register_active_dev_commands(application)\n"
    if "register_active_dev_commands(app)" in src or "register_active_dev_commands(application)" in src:
        return "exists", src
    # prefer application then app
    if re.search(r"\bapp\s*=", src) and not re.search(r"\bapplication\s*=", src):
        call = "    register_active_dev_commands(app)\n"
    m = re.search(r"^(\s*)(.*\.(?:run_polling|run)\()", src, re.M)
    if m:
        src = src[: m.start()] + call + src[m.start() :]
    else:
        # after last add_handler
        lines = src.splitlines(keepends=True)
        last = -1
        for i, ln in enumerate(lines):
            if "add_handler" in ln:
                last = i
        if last >= 0:
            lines.insert(last + 1, call)
            src = "".join(lines)
        else:
            src = src.rstrip() + "\n" + call
    return "ok", src


class ActiveDevEngine:
    def apply(
        self,
        root: str | Path,
        text: str,
        contract: RepoContract | None = None,
    ) -> ActiveDevReport:
        root = Path(root).resolve()
        if not root.is_dir():
            return ActiveDevReport(ok=False, message="مسار المستودع غير موجود")

        text = (text or "").strip()
        if len(text) < 8:
            return ActiveDevReport(ok=False, message="المواصفة قصيرة جداً للتطوير الجاد")

        if contract is None:
            contract = understand_repo(root)

        # 1) Deep formal extract (supports long structured Arabic/English)
        try:
            spec = extract_formal_spec(text)
        except Exception as e:
            return ActiveDevReport(
                ok=False,
                message=f"فشل استخراج المواصفة: {type(e).__name__}: {e}",
                contract=contract,
            )

        applied: list[AppliedChange] = []
        skipped: list[str] = []
        needs_manual: list[str] = []
        changed: list[str] = []

        existing = _existing_commands(contract)
        fw = _primary_fw(contract)
        entry = _find_entry(root, contract)

        # 2) Commands diff
        wanted: list[tuple[str, str]] = []
        for c in (spec.ui.commands if spec.ui else []) or []:
            name = _norm_cmd(getattr(c, "command", "") or "")
            if not name or len(name) < 1:
                continue
            desc = getattr(c, "description", None) or name
            if name in existing:
                skipped.append(f"الأمر /{name} موجود مسبقاً")
            else:
                wanted.append((name, desc))

        # Also extract bare /commands from text if extractor missed
        for m in re.finditer(r"/([a-zA-Z][a-zA-Z0-9_]{1,30})", text):
            name = _norm_cmd(m.group(1))
            if name and name not in existing and name not in {w[0] for w in wanted}:
                if name not in ("start", "help") or name not in existing:
                    wanted.append((name, name))

        if not entry:
            needs_manual.append("لا توجد نقطة دخول — لا يمكن تسجيل الأوامر تلقائياً")
        elif not contract.is_telegram_bot and fw == "ptb" and not contract.frameworks:
            needs_manual.append("المستودع غير مصنّف كبوت تليجرام بوضوح — التنفيذ محدود")

        # 3) Apply packages first
        pkgs = _packages_from_spec(spec, text)
        added_pkgs = _ensure_requirements(root, pkgs)
        if added_pkgs:
            applied.append(AppliedChange(
                kind="requirements",
                target="requirements.txt",
                detail="أُضيف: " + ", ".join(added_pkgs),
            ))
            changed.append("requirements.txt")

        # 4) Apply commands
        new_cmds_applied: list[tuple[str, str]] = []
        use_module = len(wanted) >= 3 and fw == "ptb" and entry is not None

        if use_module and entry is not None:
            mod_path, err = _write_commands_module(root, fw, wanted)
            if mod_path is None:
                needs_manual.append(f"فشل إنشاء وحدة الأوامر: {err}")
            else:
                status, new_src = _wire_register_module(entry)
                ok, werr = _safe_write(entry, new_src) if status != "exists" else (True, "")
                if status == "exists" or ok:
                    applied.append(AppliedChange(
                        kind="commands_module",
                        target=str(mod_path.relative_to(root)),
                        detail=f"{len(wanted)} أوامر في وحدة منفصلة",
                    ))
                    changed.append(str(mod_path.relative_to(root)))
                    if status != "exists":
                        changed.append(str(entry.relative_to(root)))
                        applied.append(AppliedChange(
                            kind="wire_register",
                            target=str(entry.relative_to(root)),
                            detail="register_active_dev_commands",
                        ))
                    new_cmds_applied = list(wanted)
                else:
                    needs_manual.append(f"فشل ربط وحدة الأوامر: {werr}")
        elif entry is not None:
            for cmd, desc in wanted[:15]:
                try:
                    if fw == "aiogram":
                        status, new_src = _aiogram_inject(entry, cmd, desc)
                    elif fw == "telebot":
                        status, new_src = _telebot_inject(entry, cmd, desc)
                    else:
                        status, new_src = _inject_ptb_command(entry, cmd, desc)
                    if status == "exists":
                        skipped.append(f"/{cmd} مسجّل مسبقاً في الكود")
                        continue
                    ok, err = _safe_write(entry, new_src)
                    if not ok:
                        needs_manual.append(f"/{cmd} رُفض بسبب SyntaxError: {err}")
                        continue
                    applied.append(AppliedChange(
                        kind="add_command",
                        target=str(entry.relative_to(root)),
                        detail=f"/{cmd} — {desc[:80]}",
                    ))
                    new_cmds_applied.append((cmd, desc))
                    if str(entry.relative_to(root)) not in changed:
                        changed.append(str(entry.relative_to(root)))
                except Exception as e:
                    needs_manual.append(f"/{cmd} فشل: {type(e).__name__}: {e}")

        # 5) Features that cannot be fully auto-coded yet
        for feat in (spec.features or [])[:30]:
            fname = getattr(feat, "name", "") or getattr(feat, "feature_id", "") or ""
            if not fname:
                continue
            # if feature implies more than a command
            needs_manual.append(
                f"ميزة «{fname}» تحتاج تصميم منطق أعمال (نسخة برو: توليد وحدات كاملة)"
            )

        if getattr(spec, "requires_payments", False):
            needs_manual.append("المدفوعات: لسه مفيش مزود دفع مكتمل تلقائياً — أُضيفت تبعيات أساسية فقط إن وُجدت")
        if getattr(spec, "requires_admin_panel", False):
            needs_manual.append("لوحة أدمن كاملة تحتاج توليد شاشات/صلاحيات أعمق")

        # 6) Rescan
        new_contract = understand_repo(root, remote_url=(contract.remote_url or ""))

        ok = bool(applied) and not any(not a.ok for a in applied)
        if not applied and not skipped:
            ok = False
            msg = "لم يُستخرج من المواصفة ما يمكن تنفيذه تلقائياً على هذا المستودع."
        elif applied:
            msg = f"تم تطبيق {len(applied)} تغيير حقيقي على المستودع."
        else:
            msg = "لم يُضف جديد (غالباً الأوامر موجودة)."
            ok = True

        return ActiveDevReport(
            ok=ok,
            message=msg,
            spec_name=getattr(spec, "bot_name", "") or "",
            applied=applied,
            skipped=skipped,
            needs_manual=needs_manual[:25],
            changed_files=changed,
            contract=new_contract,
            data={
                "commands_wanted": [c for c, _ in wanted],
                "commands_applied": [c for c, _ in new_cmds_applied],
                "framework": fw,
                "packages_added": added_pkgs,
            },
        )


def apply_development_request(
    root: str | Path,
    text: str,
    contract_dict: dict | None = None,
) -> ActiveDevReport:
    contract = None
    if contract_dict:
        try:
            contract = RepoContract.model_validate(contract_dict)
        except Exception:
            contract = None
    return ActiveDevEngine().apply(root, text, contract=contract)
