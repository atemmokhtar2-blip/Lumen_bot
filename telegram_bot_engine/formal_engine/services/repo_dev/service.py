"""
RepoDevService — act on an understood repository (not just describe it).

Deterministic capabilities (no LLM):
  - explain / structure
  - list commands
  - add command (PTB / aiogram / telebot patterns)
  - re-scan after edit
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...schemas.repo_contract import RepoContract
from ..repo_understanding import understand_repo


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
    """
    Returns (action, params).
    actions: explain | list_commands | add_command | rescan | help | unknown
    """
    t = _norm(text)
    params: dict[str, Any] = {}

    # add command: أضف أمر /stats  | add command stats | ضيف امر status
    m = re.search(
        r"(?:أضف|اضف|ضيف|add)\s*(?:أمر|امر|command)?\s*/?\s*([a-zA-Z][a-zA-Z0-9_]{1,30})",
        text,
        re.I,
    )
    if not m:
        m = re.search(r"(?:أضف|اضف|ضيف|add)\s+/?([a-zA-Z][a-zA-Z0-9_]{1,30})\s*(?:أمر|امر|command)?", text, re.I)
    if m and any(k in t for k in ("أمر", "امر", "command", "اضف", "أضف", "ضيف", "add")):
        params["command"] = m.group(1).lower().lstrip("/")
        return "add_command", params

    if any(k in t for k in ("اشرح", "شرح", "هيكل", "structure", "explain", "وصف المستودع", "فهم المستودع")):
        return "explain", params

    if any(k in t for k in ("الأوامر", "الاوامر", "list commands", "ما هي الأوامر", "ايه الأوامر", "show commands")):
        return "list_commands", params

    if any(k in t for k in ("أعد المسح", "اعادة المسح", "امسح تاني", "rescan", "حدّث الفهم", "حدث الفهم")):
        return "rescan", params

    if any(k in t for k in ("ساعد", "help", "ماذا تستطيع", "تقدر تعمل ايه", "capabilities")):
        return "help", params

    # soft: "عدل" without specific capability yet
    if any(k in t for k in ("عدل", "عدّل", "modify", "change", "طور", "طوّر", "fix")):
        return "unsupported_edit", params

    return "unknown", params


def _primary_framework(contract: RepoContract) -> str:
    fws = [f.lower() for f in contract.frameworks]
    if any("aiogram" in f for f in fws):
        return "aiogram"
    if any("telebot" in f or "pytelegrambotapi" in f for f in fws):
        return "telebot"
    if any("python-telegram-bot" in f or f == "telegram" for f in fws):
        return "ptb"
    if contract.is_telegram_bot:
        return "ptb"  # default attempt
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


def _already_has_command(contract: RepoContract, name: str) -> bool:
    return name.lower() in {c.name.lower() for c in contract.commands}


def _add_command_ptb(path: Path, cmd: str) -> str:
    src = path.read_text(encoding="utf-8")
    func = f"{cmd}_cmd"
    if f'CommandHandler("{cmd}"' in src or f"CommandHandler('{cmd}'" in src:
        return "exists"

    handler_fn = f'''
async def {func}(update, context):
    await update.message.reply_text("{cmd} works")
'''
    # insert function before main/def main or at end
    if f"async def {func}" not in src and f"def {func}" not in src:
        if "if __name__" in src:
            src = src.replace("if __name__", handler_fn + "\n\nif __name__", 1)
        else:
            src += "\n" + handler_fn

    # register near other CommandHandler
    reg = f'    app.add_handler(CommandHandler("{cmd}", {func}))\n'
    alt_reg = f'    application.add_handler(CommandHandler("{cmd}", {func}))\n'
    if "app.add_handler(CommandHandler" in src:
        # after last CommandHandler add_handler line involving CommandHandler
        lines = src.splitlines(keepends=True)
        last = -1
        for i, line in enumerate(lines):
            if "CommandHandler" in line and "add_handler" in line:
                last = i
        if last >= 0:
            lines.insert(last + 1, reg.replace("app.", "app.") if "app.add_handler" in lines[last] else alt_reg)
            # match variable name from last line
            if "application.add_handler" in lines[last]:
                lines[last + 1] = alt_reg
            elif "app.add_handler" in lines[last]:
                lines[last + 1] = reg
            src = "".join(lines)
        else:
            src += "\n" + reg
    elif "application.add_handler" in src:
        lines = src.splitlines(keepends=True)
        last = -1
        for i, line in enumerate(lines):
            if "CommandHandler" in line and "add_handler" in line:
                last = i
        if last >= 0:
            lines.insert(last + 1, alt_reg)
            src = "".join(lines)
        else:
            src += "\n" + alt_reg
    else:
        # cannot register safely
        path.write_text(src, encoding="utf-8")
        return "handler_added_no_register"

    if "CommandHandler" not in src.split(handler_fn)[0] and "from telegram.ext import" in src:
        # ensure import
        if "CommandHandler" not in src:
            src = src.replace(
                "from telegram.ext import",
                "from telegram.ext import CommandHandler,",
                1,
            )
    path.write_text(src, encoding="utf-8")
    return "ok"


def _add_command_aiogram(path: Path, cmd: str) -> str:
    src = path.read_text(encoding="utf-8")
    if f'Command("{cmd}")' in src or f"Command('{cmd}')" in src:
        return "exists"
    block = f'''

@router.message(Command("{cmd}"))
async def {cmd}_handler(message: Message):
    await message.answer("{cmd} works")
'''
    # ensure imports
    if "Command" not in src and "from aiogram.filters import" in src:
        src = src.replace(
            "from aiogram.filters import",
            "from aiogram.filters import Command,",
            1,
        )
    elif "from aiogram.filters import Command" not in src and "CommandStart" in src:
        src = src.replace(
            "from aiogram.filters import CommandStart",
            "from aiogram.filters import CommandStart, Command",
            1,
        )
    elif "from aiogram.filters import" not in src:
        src = "from aiogram.filters import Command\n" + src

    if "from aiogram.types import Message" not in src and "Message" not in src:
        src = "from aiogram.types import Message\n" + src

    if "@router.message" in src:
        # append after last router handler block — before async def main
        if "async def main" in src:
            src = src.replace("async def main", block + "\n\nasync def main", 1)
        else:
            src += block
    else:
        src += block
    path.write_text(src, encoding="utf-8")
    return "ok"


def _add_command_telebot(path: Path, cmd: str) -> str:
    src = path.read_text(encoding="utf-8")
    if f"commands=['{cmd}']" in src or f'commands=["{cmd}"]' in src or f"/{cmd}" in src and cmd in src:
        # weak exists check
        if re.search(rf"commands\s*=\s*\[[^\]]*['\"]{cmd}['\"]", src):
            return "exists"
    block = f'''

@bot.message_handler(commands=['{cmd}'])
def {cmd}_handler(message):
    bot.reply_to(message, "{cmd} works")
'''
    if "infinity_polling" in src:
        src = src.replace("bot.infinity_polling", block + "\n\nbot.infinity_polling", 1)
    elif "polling" in src:
        src = src.replace("bot.polling", block + "\n\nbot.polling", 1)
    else:
        src += block
    path.write_text(src, encoding="utf-8")
    return "ok"


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
                    "على المستودع النشط أقدر حالياً:\n"
                    "• اشرح هيكل المشروع\n"
                    "• اعرض الأوامر المكتشفة\n"
                    "• أضف أمر بسيط (مثل: أضف أمر /stats)\n"
                    "• أعد مسح المستودع بعد التعديل\n\n"
                    "تعديلات معقدة (إعادة هيكلة، منطق أعمال كامل) لسه قيد البناء — "
                    "هتتنفذ خطوة بخطوة بجودة عالية مش وعود فاضي."
                ),
                contract=contract,
            )

        if action == "explain":
            return RepoDevResult(
                ok=True,
                action="explain",
                message=contract.to_user_summary(),
                contract=contract,
            )

        if action == "list_commands":
            if not contract.commands:
                msg = "لم يُكتشف تسجيل أوامر واضح في المستودع."
            else:
                lines = ["الأوامر المكتشفة:"]
                for c in contract.commands:
                    lines.append(f"• /{c.name} — `{c.source_file}` ({c.registration})")
                msg = "\n".join(lines)
            return RepoDevResult(ok=True, action="list_commands", message=msg, contract=contract)

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
                    "طلب التعديل مفهوم، لكن نوع التعديل ده لسه مش مدعوم بشكل آمن.\n"
                    "المدعوم الآن: إضافة أمر بسيط، شرح الهيكل، عرض الأوامر، إعادة المسح.\n"
                    "مثال: أضف أمر /stats"
                ),
                contract=contract,
            )

        if action == "add_command":
            cmd = (params.get("command") or "").lower()
            if not cmd:
                return RepoDevResult(ok=False, action="add_command", message="حدد اسم الأمر، مثال: أضف أمر /stats")
            if not contract.is_telegram_bot and contract.architecture_style not in ("telegram_bot", "generation_engine"):
                return RepoDevResult(
                    ok=False,
                    action="add_command",
                    message="المستودع مش متصنف كبوت تليجرام تطبيقي — إضافة أمر مش آمنة هنا.",
                    contract=contract,
                )
            if _already_has_command(contract, cmd):
                return RepoDevResult(
                    ok=True,
                    action="add_command",
                    message=f"الأمر /{cmd} موجود بالفعل حسب المسح.",
                    contract=contract,
                )

            entry = _find_entry_file(root, contract)
            if entry is None:
                return RepoDevResult(
                    ok=False,
                    action="add_command",
                    message="لم أجد ملف دخول مناسب (main.py / bot.py) للتعديل.",
                    contract=contract,
                )

            fw = _primary_framework(contract)
            try:
                if fw == "aiogram":
                    status = _add_command_aiogram(entry, cmd)
                elif fw == "telebot":
                    status = _add_command_telebot(entry, cmd)
                else:
                    status = _add_command_ptb(entry, cmd)
            except Exception as e:
                return RepoDevResult(
                    ok=False,
                    action="add_command",
                    message=f"فشل التعديل: {type(e).__name__}: {e}",
                    contract=contract,
                )

            # re-scan
            new_contract = understand_repo(root, remote_url=contract.remote_url or "")
            if status == "exists":
                msg = f"/{cmd} كان موجوداً."
            elif status == "handler_added_no_register":
                msg = (
                    f"أضفت دالة الأمر /{cmd} في `{entry.name}` لكن التسجيل التلقائي غير مؤكد. "
                    "راجع الملف."
                )
            else:
                msg = f"تم إضافة /{cmd} في `{entry.relative_to(root)}` (إطار: {fw})."
            if cmd in {c.name for c in new_contract.commands}:
                msg += "\n✓ المسح الجديد يرى الأمر."
            else:
                msg += "\n⚠ المسح الجديد لسه ما شافش الأمر — قد يحتاج تسجيل يدوي."

            return RepoDevResult(
                ok=True,
                action="add_command",
                message=msg,
                changed_files=[str(entry.relative_to(root))],
                contract=new_contract,
            )

        # unknown on active repo — do not pretend we generated anything
        return RepoDevResult(
            ok=False,
            action="unknown",
            message=(
                "عندي مستودع نشط، لكن لم أفهم طلب التطوير بدقة.\n"
                "جرّب:\n"
                "• اشرح الهيكل\n"
                "• الأوامر\n"
                "• أضف أمر /stats\n"
                "• أعد المسح"
            ),
            contract=contract,
        )


def handle_repo_request(text: str, repo_path: str, contract_dict: dict | None = None) -> RepoDevResult:
    return RepoDevService().run(text, repo_path, contract_dict)
