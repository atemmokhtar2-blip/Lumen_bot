"""
RepoDevService v2 — deterministic development actions on an active repository.

Capabilities (no LLM):
  explain | list_commands | list_files | show_file | search
  add_command | remove_command | rescan | help
  project_status (what is this project)

Every file edit is syntax-checked with ast.parse when target is Python.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...schemas.repo_contract import RepoContract
from ..repo_understanding import understand_repo

_SKIP = {".git", "__pycache__", ".venv", "venv", "node_modules", ".mypy_cache"}


@dataclass
class RepoDevResult:
    ok: bool
    action: str
    message: str
    changed_files: list[str] = field(default_factory=list)
    contract: RepoContract | None = None
    data: dict[str, Any] = field(default_factory=dict)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def detect_repo_intent(text: str) -> tuple[str, dict[str, Any]]:
    t = _norm(text)
    params: dict[str, Any] = {}
    raw = text or ""

    # show file: اعرض ملف main.py | show file bot.py | افتح handlers/start.py
    m = re.search(
        r"(?:اعرض|افتح|show|open|اقرأ|اقرا)\s*(?:ملف|file)?\s*[`\"']?([A-Za-z0-9_./\\-]+\.py)[`\"']?",
        raw,
        re.I,
    )
    if m:
        params["path"] = m.group(1).replace("\\", "/")
        return "show_file", params

    # search: ابحث عن CommandHandler | search start_handler
    m = re.search(
        r"(?:ابحث|بحث|search|find)\s*(?:عن)?\s*[`\"']?([^`\"'\n]{2,60})[`\"']?",
        raw,
        re.I,
    )
    if m and any(k in t for k in ("ابحث", "بحث", "search", "find")):
        params["query"] = m.group(1).strip()
        return "search", params

    # remove command
    m = re.search(
        r"(?:احذف|امسح|remove|delete)\s*(?:أمر|امر|command)?\s*/?\s*([a-zA-Z][a-zA-Z0-9_]{1,30})",
        raw,
        re.I,
    )
    if m and any(k in t for k in ("احذف", "امسح", "remove", "delete")):
        params["command"] = m.group(1).lower().lstrip("/")
        return "remove_command", params

    # add command
    m = re.search(
        r"(?:أضف|اضف|ضيف|add)\s*(?:أمر|امر|command)?\s*/?\s*([a-zA-Z][a-zA-Z0-9_]{1,30})",
        raw,
        re.I,
    )
    if not m:
        m = re.search(
            r"(?:أضف|اضف|ضيف|add)\s+/?([a-zA-Z][a-zA-Z0-9_]{1,30})\s*(?:أمر|امر|command)?",
            raw,
            re.I,
        )
    if m and any(k in t for k in ("أمر", "امر", "command", "اضف", "أضف", "ضيف", "add")):
        params["command"] = m.group(1).lower().lstrip("/")
        return "add_command", params

    if any(k in t for k in ("قائمة الملفات", "الملفات", "list files", "شجرة", "tree", "files")):
        return "list_files", params

    if any(k in t for k in ("اشرح", "شرح", "هيكل", "structure", "explain", "وصف المستودع", "فهم المستودع", "ما هذا", "ما هذا المشروع", "ايه المشروع")):
        return "explain", params

    if any(k in t for k in ("الأوامر", "الاوامر", "list commands", "ما هي الأوامر", "ايه الأوامر", "show commands")):
        return "list_commands", params

    if any(k in t for k in ("أعد المسح", "اعادة المسح", "امسح تاني", "rescan", "حدّث الفهم", "حدث الفهم", "حدث المسح")):
        return "rescan", params

    if any(k in t for k in ("حالة", "status", "ماذا تستطيع", "تقدر تعمل ايه", "capabilities", "ساعد", "help")):
        return "help", params

    # Phase-2 development intelligence
    if any(k in t for k in (
        "سد فجوات", "سد الفجوات", "أضف التبعيات", "اضف التبعيات",
        "apply deps", "fix deps", "dependency gaps", "فجوات التبعيات",
    )):
        return "apply_deps", params

    if any(k in t for k in (
        "أين أعدل", "اين اعدل", "أين أعدّل", "اماكن التعديل", "أهداف التعديل",
        "where to edit", "edit targets", "سطح التعديل",
    )):
        return "edit_targets", params

    if any(k in t for k in (
        "نفذ المواصفة", "نفّذ المواصفة", "طبق المواصفة", "طبّق المواصفة",
        "apply spec", "implement spec", "نفذ التطوير", "نفّذ التطوير",
    )):
        return "apply_dev", params

    # Long development specs (>180 chars) with structure signals → full engine
    if len(raw) >= 180 and any(
        k in t for k in (
            "أمر", "امر", "command", "ميزة", "feature", "زر", "button",
            "أضف", "اضف", "طور", "طوّر", "يجب", "المواصفات", "spec",
            "admin", "أدمن", "دفع", "payment", "ai", "ذكي",
        )
    ):
        return "apply_dev", params

    if any(k in t for k in (
        "خطة تطوير", "خطة التطوير", "dev plan", "develop plan",
        "طور المستودع", "طوّر المستودع", "تطوير المستودع",
        "عايز اطور", "عايز أطور", "أريد تطوير", "develop repo",
        "ملخص تطوير", "تطوير نشط", "dev brief", "وضع التطوير",
    )):
        # short "طور المستودع" → plan; long already caught above
        if len(raw) >= 180:
            return "apply_dev", params
        return "dev_plan", params

    if any(k in t for k in ("عدل", "عدّل", "modify", "change", "طور", "طوّر", "fix", "أصلح", "صلح")):
        return "dev_plan", params

    return "unknown", params


def _primary_framework(contract: RepoContract) -> str:
    fws = [f.lower() for f in contract.frameworks]
    if any("aiogram" in f for f in fws):
        return "aiogram"
    if any("telebot" in f or "pytelegrambotapi" in f for f in fws):
        return "telebot"
    if any("python-telegram-bot" in f for f in fws):
        return "ptb"
    if contract.is_telegram_bot:
        return "ptb"
    return "unknown"


def _find_entry_file(root: Path, contract: RepoContract) -> Path | None:
    for e in contract.entry_points:
        p = root / e.path
        if p.exists() and p.suffix == ".py":
            return p
    for name in ("main.py", "bot.py", "app.py"):
        p = root / name
        if p.exists():
            return p
    return None


def _syntax_ok(path: Path) -> tuple[bool, str]:
    if path.suffix != ".py":
        return True, ""
    try:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        return True, ""
    except SyntaxError as e:
        return False, f"{e.msg} line {e.lineno}"


def _safe_write(path: Path, content: str) -> tuple[bool, str]:
    try:
        ast.parse(content, filename=str(path))
    except SyntaxError as e:
        return False, f"رفضت الكتابة — SyntaxError: {e.msg} line {e.lineno}"
    path.write_text(content, encoding="utf-8")
    return True, ""


def _already_has_command(contract: RepoContract, name: str) -> bool:
    return name.lower() in {c.name.lower() for c in contract.commands}


def _add_command_ptb(path: Path, cmd: str) -> tuple[str, str]:
    src = path.read_text(encoding="utf-8")
    if f'CommandHandler("{cmd}"' in src or f"CommandHandler('{cmd}'" in src:
        return "exists", src
    func = f"{cmd}_cmd"
    handler_fn = f'''

async def {func}(update, context):
    await update.message.reply_text("{cmd} works")
'''
    if f"async def {func}" not in src and f"def {func}" not in src:
        if "if __name__" in src:
            src = src.replace("if __name__", handler_fn + "\n\nif __name__", 1)
        else:
            src += handler_fn

    lines = src.splitlines(keepends=True)
    last = -1
    var = "app"
    for i, line in enumerate(lines):
        if "CommandHandler" in line and "add_handler" in line:
            last = i
            if "application.add_handler" in line:
                var = "application"
            elif "app.add_handler" in line:
                var = "app"
    reg = f'    {var}.add_handler(CommandHandler("{cmd}", {func}))\n'
    if last >= 0:
        lines.insert(last + 1, reg)
        src = "".join(lines)
    elif "CommandHandler" in src:
        src += "\n" + reg
    else:
        if "from telegram.ext import" in src and "CommandHandler" not in src:
            src = src.replace("from telegram.ext import", "from telegram.ext import CommandHandler,", 1)
        src += "\n" + reg
    return "ok", src


def _add_command_aiogram(path: Path, cmd: str) -> tuple[str, str]:
    src = path.read_text(encoding="utf-8")
    if f'Command("{cmd}")' in src or f"Command('{cmd}')" in src:
        return "exists", src
    block = f'''

@router.message(Command("{cmd}"))
async def {cmd}_handler(message: Message):
    await message.answer("{cmd} works")
'''
    if "from aiogram.filters import" in src and "Command" not in src.split("\n")[0:30].__str__() if False else True:
        if re.search(r"from aiogram\.filters import ([^\n]+)", src):
            if "Command" not in src:
                src = re.sub(
                    r"from aiogram\.filters import ([^\n]+)",
                    lambda m: m.group(0) if "Command" in m.group(1) else f"from aiogram.filters import {m.group(1)}, Command",
                    src,
                    count=1,
                )
        if "CommandStart" in src and "Command," not in src and ", Command" not in src and "import Command" not in src:
            src = src.replace(
                "from aiogram.filters import CommandStart",
                "from aiogram.filters import CommandStart, Command",
                1,
            )
    if "from aiogram.filters import" not in src:
        src = "from aiogram.filters import Command\n" + src
    if "Message" not in src:
        src = "from aiogram.types import Message\n" + src
    if "async def main" in src:
        src = src.replace("async def main", block + "\n\nasync def main", 1)
    else:
        src += block
    return "ok", src


def _add_command_telebot(path: Path, cmd: str) -> tuple[str, str]:
    src = path.read_text(encoding="utf-8")
    if re.search(rf"commands\s*=\s*\[[^\]]*['\"]{cmd}['\"]", src):
        return "exists", src
    block = f'''

@bot.message_handler(commands=['{cmd}'])
def {cmd}_handler(message):
    bot.reply_to(message, "{cmd} works")
'''
    if "infinity_polling" in src:
        src = src.replace("bot.infinity_polling", block + "\n\nbot.infinity_polling", 1)
    elif "bot.polling" in src:
        src = src.replace("bot.polling", block + "\n\nbot.polling", 1)
    else:
        src += block
    return "ok", src


def _remove_command_from_file(path: Path, cmd: str, fw: str) -> tuple[str, str]:
    src = path.read_text(encoding="utf-8")
    original = src
    if fw == "ptb":
        src = re.sub(
            rf'.*add_handler\(\s*CommandHandler\(\s*["\']{cmd}["\'].*\n',
            "",
            src,
        )
        src = re.sub(
            rf'\nasync def {cmd}_cmd\([\s\S]*?(?=\nasync def |\ndef |\nif __name__|\Z)',
            "\n",
            src,
            count=1,
        )
    elif fw == "aiogram":
        src = re.sub(
            rf'\n@router\.message\(Command\(["\']{cmd}["\']\)\)\nasync def {cmd}_handler[\s\S]*?(?=\n@|\nasync def |\ndef |\Z)',
            "\n",
            src,
            count=1,
        )
    elif fw == "telebot":
        src = re.sub(
            rf'\n@bot\.message_handler\(commands=\[[^\]]*{cmd}[^\]]*\]\)\ndef {cmd}_handler[\s\S]*?(?=\n@|\ndef |\Z)',
            "\n",
            src,
            count=1,
        )
    if src == original:
        return "not_found", original
    return "ok", src


def _list_files(root: Path, limit: int = 40) -> list[str]:
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(x in p.parts for x in _SKIP):
            continue
        rel = str(p.relative_to(root)).replace("\\", "/")
        out.append(rel)
        if len(out) >= limit:
            break
    return out


def _search(root: Path, query: str, limit: int = 20) -> list[str]:
    hits = []
    q = query.strip()
    if not q:
        return hits
    for p in root.rglob("*.py"):
        if any(x in p.parts for x in _SKIP):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if q in line:
                rel = str(p.relative_to(root)).replace("\\", "/")
                hits.append(f"{rel}:{i}: {line.strip()[:120]}")
                if len(hits) >= limit:
                    return hits
    return hits


class RepoDevService:
    def run(
        self,
        text: str,
        repo_path: str | Path,
        contract_dict: dict | None = None,
    ) -> RepoDevResult:
        root = Path(repo_path)
        if not root.exists():
            return RepoDevResult(ok=False, action="error", message="مسار المستودع غير موجود")

        contract = None
        if contract_dict:
            try:
                contract = RepoContract.model_validate(contract_dict)
            except Exception:
                contract = None
        if contract is None:
            contract = understand_repo(root)

        action, params = detect_repo_intent(text)

        if action == "help":
            return RepoDevResult(
                ok=True,
                action="help",
                message=(
                    "🔧 *قدرات التطوير على المستودع النشط (بعد الفهم الكامل)*\n"
                    "• اشرح الهيكل / ما هذا المشروع\n"
                    "• الأوامر — عرض الأوامر المكتشفة\n"
                    "• قائمة الملفات\n"
                    "• اعرض ملف main.py\n"
                    "• ابحث عن CommandHandler\n"
                    "• أضف أمر /stats\n"
                    "• احذف أمر /stats\n"
                    "• أعد المسح\n\n"
                    "أي تعديل معقد غير مدعوم يُرفض بصراحة بدل تنفيذ عشوائي."
                ),
                contract=contract,
            )

        if action == "explain":
            return RepoDevResult(ok=True, action="explain", message=contract.to_user_summary(), contract=contract)

        if action == "list_commands":
            if not contract.commands:
                msg = "لم يُكتشف تسجيل أوامر واضح."
            else:
                lines = ["الأوامر المكتشفة:"]
                for c in contract.commands:
                    lines.append(f"• /{c.name} — `{c.source_file}` ({c.registration or '—'})")
                msg = "\n".join(lines)
            return RepoDevResult(ok=True, action="list_commands", message=msg, contract=contract)

        if action == "list_files":
            files = _list_files(root)
            msg = "ملفات (عينة):\n" + "\n".join(f"• `{f}`" for f in files)
            if len(files) >= 40:
                msg += "\n…"
            return RepoDevResult(ok=True, action="list_files", message=msg, contract=contract)

        if action == "show_file":
            rel = params.get("path") or ""
            path = (root / rel).resolve()
            if not str(path).startswith(str(root.resolve())):
                return RepoDevResult(ok=False, action="show_file", message="مسار غير مسموح", contract=contract)
            if not path.exists() or not path.is_file():
                return RepoDevResult(ok=False, action="show_file", message=f"الملف غير موجود: `{rel}`", contract=contract)
            content = path.read_text(encoding="utf-8", errors="ignore")
            if len(content) > 3500:
                content = content[:3500] + "\n\n… (مقتطف)"
            return RepoDevResult(
                ok=True,
                action="show_file",
                message=f"📄 `{rel}`\n```\n{content}\n```",
                contract=contract,
            )

        if action == "search":
            q = params.get("query") or ""
            hits = _search(root, q)
            if not hits:
                msg = f"لا نتائج لـ `{q}`"
            else:
                msg = f"نتائج البحث عن `{q}`:\n" + "\n".join(f"• `{h}`" for h in hits)
            return RepoDevResult(ok=True, action="search", message=msg, contract=contract, data={"hits": hits})

        if action == "rescan":
            contract = understand_repo(root, remote_url=contract.remote_url or "")
            return RepoDevResult(
                ok=True,
                action="rescan",
                message="تم إعادة المسح:\n" + contract.to_user_summary(),
                contract=contract,
            )

        if action == "unsupported_edit":
            return RepoDevResult(
                ok=False,
                action="unsupported_edit",
                message=(
                    "طلب التعديل مفهوم، لكن النوع ده لسه مش مدعوم بشكل آمن.\n"
                    "المدعوم: إضافة/حذف أمر، عرض ملف، بحث، شرح، إعادة مسح.\n"
                    "مثال: أضف أمر /stats"
                ),
                contract=contract,
            )

        if action == "add_command":
            cmd = (params.get("command") or "").lower()
            if not cmd:
                return RepoDevResult(ok=False, action="add_command", message="حدد اسم الأمر، مثال: أضف أمر /stats", contract=contract)
            if contract.architecture_style == "library":
                return RepoDevResult(ok=False, action="add_command", message="هذا المستودع مكتبة وليس بوت تطبيقي — لن أعدّل عليه كأمر بوت.", contract=contract)
            if _already_has_command(contract, cmd):
                return RepoDevResult(ok=True, action="add_command", message=f"/{cmd} موجود بالفعل.", contract=contract)
            entry = _find_entry_file(root, contract)
            if entry is None:
                return RepoDevResult(ok=False, action="add_command", message="لا يوجد ملف دخول مناسب للتعديل.", contract=contract)
            fw = _primary_framework(contract)
            try:
                if fw == "aiogram":
                    status, new_src = _add_command_aiogram(entry, cmd)
                elif fw == "telebot":
                    status, new_src = _add_command_telebot(entry, cmd)
                else:
                    status, new_src = _add_command_ptb(entry, cmd)
            except Exception as e:
                return RepoDevResult(ok=False, action="add_command", message=f"فشل: {type(e).__name__}: {e}", contract=contract)
            if status == "exists":
                return RepoDevResult(ok=True, action="add_command", message=f"/{cmd} موجود في الملف.", contract=contract)
            ok, err = _safe_write(entry, new_src)
            if not ok:
                return RepoDevResult(ok=False, action="add_command", message=err, contract=contract)
            new_contract = understand_repo(root, remote_url=contract.remote_url or "")
            seen = cmd in {c.name for c in new_contract.commands}
            msg = f"تم إضافة /{cmd} في `{entry.relative_to(root)}` (إطار: {fw})."
            msg += "\n✓ المسح يرى الأمر." if seen else "\n⚠ المسح لسه ما شافش الأمر — راجع التسجيل."
            return RepoDevResult(
                ok=True,
                action="add_command",
                message=msg,
                changed_files=[str(entry.relative_to(root))],
                contract=new_contract,
            )

        if action == "remove_command":
            cmd = (params.get("command") or "").lower()
            if not cmd:
                return RepoDevResult(ok=False, action="remove_command", message="حدد الأمر، مثال: احذف أمر /stats", contract=contract)
            entry = _find_entry_file(root, contract)
            if entry is None:
                return RepoDevResult(ok=False, action="remove_command", message="لا يوجد ملف دخول.", contract=contract)
            fw = _primary_framework(contract)
            status, new_src = _remove_command_from_file(entry, cmd, fw)
            if status == "not_found":
                return RepoDevResult(ok=False, action="remove_command", message=f"لم أجد /{cmd} بشكل قابل للحذف التلقائي في `{entry.name}`.", contract=contract)
            ok, err = _safe_write(entry, new_src)
            if not ok:
                return RepoDevResult(ok=False, action="remove_command", message=err, contract=contract)
            new_contract = understand_repo(root, remote_url=contract.remote_url or "")
            return RepoDevResult(
                ok=True,
                action="remove_command",
                message=f"تم حذف /{cmd} من `{entry.relative_to(root)}` (أفضل جهد حتمي).",
                changed_files=[str(entry.relative_to(root))],
                contract=new_contract,
            )


        if action == "apply_dev":
            from ..active_dev import apply_development_request
            report = apply_development_request(root, text, contract_dict=contract.model_dump(mode="json"))
            return RepoDevResult(
                ok=report.ok,
                action="apply_dev",
                message=report.to_user_text(),
                changed_files=list(report.changed_files),
                contract=report.contract or contract,
                data=report.data,
            )

        if action == "dev_plan":
            from ..repo_dev_intelligence import build_dev_plan
            plan = build_dev_plan(contract, text)
            return RepoDevResult(
                ok=True,
                action="dev_plan",
                message=plan.to_user_text(),
                contract=contract,
                data={"steps": [s.id for s in plan.steps], "targets": plan.targets},
            )

        if action == "dev_brief":
            from ..repo_dev_intelligence import build_dev_plan
            plan = build_dev_plan(contract, "تطوير تكراري للمستودع النشط")
            lines = [
                "🚀 *وضع تطوير المستودع النشط*",
                contract.to_user_summary(),
                "",
                plan.to_user_text(),
            ]
            return RepoDevResult(
                ok=True,
                action="dev_brief",
                message=chr(10).join(lines),
                contract=contract,
            )

        if action == "edit_targets":
            from ..repo_dev_intelligence import suggest_edit_targets
            targets = suggest_edit_targets(contract)
            body = chr(10).join(f"• `{t}`" for t in targets) if targets else "• لا أهداف واضحة"
            msg = "🎯 *أهداف التعديل المقترحة:*" + chr(10) + body
            return RepoDevResult(
                ok=True,
                action="edit_targets",
                message=msg,
                contract=contract,
                data={"targets": targets},
            )

        if action == "apply_deps":
            from ..repo_dev_intelligence import apply_dependency_gaps
            added, msg = apply_dependency_gaps(root, contract)
            new_contract = contract
            if added:
                new_contract = understand_repo(root, remote_url=contract.remote_url or "")
            return RepoDevResult(
                ok=True,
                action="apply_deps",
                message=msg,
                changed_files=["requirements.txt"] if added else [],
                contract=new_contract,
                data={"added": added},
            )

        if action == "unsupported_edit":
            from ..repo_dev_intelligence import build_dev_plan
            plan = build_dev_plan(contract, text)
            return RepoDevResult(
                ok=True,
                action="dev_plan",
                message=plan.to_user_text(),
                contract=contract,
            )

        return RepoDevResult(
            ok=False,
            action="unknown",
            message=(
                "المستودع النشط جاهز، لكن الطلب غير معروف.\n"
                "جرّب: اشرح | الأوامر | قائمة الملفات | اعرض ملف main.py | "
                "ابحث عن X | أضف أمر /stats | احذف أمر /stats | أعد المسح"
            ),
            contract=contract,
        )


def handle_repo_request(text: str, repo_path: str, contract_dict: dict | None = None) -> RepoDevResult:
    return RepoDevService().run(text, repo_path, contract_dict)
