#!/usr/bin/env python3
"""
Test that the transpiler generates REAL Telegram API action handlers
for group management commands (ban, mute, kick, pin, delete, etc.)

Verifies:
  - Commands with action_type produce handlers that call real Telegram API methods
  - The generated handlers.py compiles
  - ban_user → chat.ban_member, mute_user → chat.restrict_member, etc.
"""

from __future__ import annotations

import py_compile
import shutil
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from telegram_bot_engine.formal_engine.schemas.rich_spec import (
    CommandKind,
    PostAction,
    RichButton,
    RichCommand,
    RichEntity,
    RichEvidence,
    RichField,
    RichSpec,
)
from telegram_bot_engine.formal_engine.spec_pipeline.spec_transpiler import transpile_spec


def _ev(quote: str, confidence: float = 0.9) -> RichEvidence:
    return RichEvidence(quote=quote, confidence=confidence)


def group_management_spec() -> RichSpec:
    """A group management bot spec with action_type commands."""
    cmds: list[RichCommand] = [
        RichCommand(
            name="start",
            kind=CommandKind.START,
            description="بدء البوت",
            reply_text="مرحباً بك في بوت إدارة المجموعات",
            evidence=_ev("أمر /start لبدء البوت"),
        ),
        RichCommand(
            name="help",
            kind=CommandKind.HELP,
            description="المساعدة",
            reply_text="قائمة الأوامر المتاحة",
            evidence=_ev("أمر /help للمساعدة"),
        ),
        RichCommand(
            name="ban",
            kind=CommandKind.ACTION,
            description="حظر مستخدم",
            action_type="ban_user",
            target_args="user_id أو الرد على رسالة المستخدم",
            admin_only=True,
            evidence=_ev("أمر /ban لحظر مستخدم"),
        ),
        RichCommand(
            name="unban",
            kind=CommandKind.ACTION,
            description="رفع الحظر",
            action_type="unban_user",
            admin_only=True,
            evidence=_ev("أمر /unban لرفع الحظر"),
        ),
        RichCommand(
            name="mute",
            kind=CommandKind.ACTION,
            description="كتم مستخدم",
            action_type="mute_user",
            target_args="مدة + سبب",
            admin_only=True,
            evidence=_ev("أمر /mute لكتم مستخدم"),
        ),
        RichCommand(
            name="unmute",
            kind=CommandKind.ACTION,
            description="رفع الكتم",
            action_type="unmute_user",
            admin_only=True,
            evidence=_ev("أمر /unmute لرفع الكتم"),
        ),
        RichCommand(
            name="kick",
            kind=CommandKind.ACTION,
            description="طرد مستخدم",
            action_type="kick_user",
            admin_only=True,
            evidence=_ev("أمر /kick لطرد مستخدم"),
        ),
        RichCommand(
            name="warn",
            kind=CommandKind.ACTION,
            description="تحذير مستخدم",
            action_type="warn_user",
            admin_only=True,
            evidence=_ev("أمر /warn لتحذير مستخدم"),
        ),
        RichCommand(
            name="warnings",
            kind=CommandKind.INFO,
            description="عرض التحذيرات",
            action_type="show_warnings",
            admin_only=True,
            evidence=_ev("أمر /warnings لعرض التحذيرات"),
        ),
        RichCommand(
            name="clearwarnings",
            kind=CommandKind.ACTION,
            description="مسح التحذيرات",
            action_type="clear_warnings",
            admin_only=True,
            evidence=_ev("أمر /clearwarnings لمسح التحذيرات"),
        ),
        RichCommand(
            name="pin",
            kind=CommandKind.ACTION,
            description="تثبيت رسالة",
            action_type="pin_message",
            admin_only=True,
            evidence=_ev("أمر /pin لتثبيت رسالة"),
        ),
        RichCommand(
            name="unpin",
            kind=CommandKind.ACTION,
            description="إلغاء تثبيت",
            action_type="unpin_message",
            admin_only=True,
            evidence=_ev("أمر /unpin لإلغاء تثبيت"),
        ),
        RichCommand(
            name="purge",
            kind=CommandKind.ACTION,
            description="حذف رسائل متعددة",
            action_type="purge_messages",
            admin_only=True,
            evidence=_ev("أمر /purge لحذف رسائل"),
        ),
        RichCommand(
            name="delete",
            kind=CommandKind.ACTION,
            description="حذف رسالة",
            action_type="delete_message",
            admin_only=True,
            evidence=_ev("أمر /delete لحذف رسالة"),
        ),
        RichCommand(
            name="lock",
            kind=CommandKind.ACTION,
            description="قفل المجموعة",
            action_type="toggle_setting",
            admin_only=True,
            evidence=_ev("أمر /lock لقفل المجموعة"),
        ),
        RichCommand(
            name="slowmode",
            kind=CommandKind.ACTION,
            description="ضبط الوضع البطيء",
            action_type="set_slowmode",
            admin_only=True,
            evidence=_ev("أمر /slowmode لضبط الوضع البطيء"),
        ),
        RichCommand(
            name="admins",
            kind=CommandKind.INFO,
            description="عرض المشرفين",
            action_type="show_admins",
            evidence=_ev("أمر /admins لعرض المشرفين"),
        ),
        RichCommand(
            name="id",
            kind=CommandKind.INFO,
            description="عرض المعرف",
            action_type="show_id",
            evidence=_ev("أمر /id لعرض المعرف"),
        ),
        RichCommand(
            name="info",
            kind=CommandKind.INFO,
            description="معلومات المستخدم",
            action_type="show_info",
            evidence=_ev("أمر /info لمعلومات المستخدم"),
        ),
        RichCommand(
            name="rules",
            kind=CommandKind.INFO,
            description="عرض القوانين",
            action_type="show_rules",
            evidence=_ev("أمر /rules لعرض القوانين"),
        ),
        RichCommand(
            name="setrules",
            kind=CommandKind.ACTION,
            description="تعيين القوانين",
            action_type="set_rules",
            admin_only=True,
            evidence=_ev("أمر /setrules لتعيين القوانين"),
        ),
        RichCommand(
            name="welcome",
            kind=CommandKind.INFO,
            description="رسالة الترحيب",
            action_type="show_welcome",
            evidence=_ev("أمر /welcome لعرض رسالة الترحيب"),
        ),
        RichCommand(
            name="setwelcome",
            kind=CommandKind.ACTION,
            description="تعيين رسالة الترحيب",
            action_type="set_welcome",
            admin_only=True,
            evidence=_ev("أمر /setwelcome لتعيين رسالة الترحيب"),
        ),
        RichCommand(
            name="report",
            kind=CommandKind.ACTION,
            description="الإبلاغ عن مستخدم",
            action_type="report_user",
            evidence=_ev("أمر /report للإبلاغ عن مستخدم"),
        ),
        RichCommand(
            name="settings",
            kind=CommandKind.INFO,
            description="عرض الإعدادات",
            action_type="show_settings",
            admin_only=True,
            evidence=_ev("أمر /settings لعرض الإعدادات"),
        ),
        RichCommand(
            name="stats",
            kind=CommandKind.STATS,
            description="إحصائيات المجموعة",
            action_type="show_stats",
            admin_only=True,
            evidence=_ev("أمر /stats للإحصائيات"),
        ),
        RichCommand(
            name="broadcast",
            kind=CommandKind.BROADCAST,
            description="بث رسالة",
            action_type="broadcast_message",
            admin_only=True,
            evidence=_ev("أمر /broadcast لبث رسالة"),
        ),
    ]

    entities = [
        RichEntity(
            name="User",
            fields=[
                RichField(name="user_id", type="int", description="Telegram user ID"),
                RichField(name="username", type="str", description="Telegram username"),
                RichField(name="warnings", type="int", description="عدد التحذيرات"),
            ],
            evidence=_ev("معلومات المستخدم"),
        ),
        RichEntity(
            name="Warning",
            fields=[
                RichField(name="user_id", type="int", description="المستخدم المحذر"),
                RichField(name="reason", type="str", description="سبب التحذير"),
                RichField(name="admin_id", type="int", description="المشرف الذي أصدر التحذير"),
            ],
            evidence=_ev("سجل التحذيرات"),
        ),
        RichEntity(
            name="GroupSetting",
            fields=[
                RichField(name="setting_key", type="str", description="اسم الإعداد"),
                RichField(name="setting_value", type="str", description="قيمة الإعداد"),
            ],
            evidence=_ev("إعدادات المجموعة"),
        ),
    ]

    buttons = [
        RichButton(label="📋 الأوامر", callback_id="cmd_help", target_command="help"),
        RichButton(label="ℹ️ المعلومات", callback_id="cmd_info", target_command="info"),
        RichButton(label="📢 القوانين", callback_id="cmd_rules", target_command="rules"),
    ]

    return RichSpec(
        bot_name="GroupManagerBot",
        raw_description="بوت إدارة المجموعات مع أوامر الحظر والكتم والطرد والتحذير",
        commands=cmds,
        entities=entities,
        buttons=buttons,
        language="ar",
    )


# Expected API calls for each action_type
EXPECTED_API_CALLS = {
    "ban_user": ["ban_member"],
    "unban_user": ["unban_member"],
    "mute_user": ["restrict_member", "ChatPermissions"],
    "unmute_user": ["restrict_member", "ChatPermissions"],
    "kick_user": ["ban_member", "unban_member"],
    "warn_user": ["store.create"],
    "show_warnings": ["store"],
    "clear_warnings": ["store"],
    "pin_message": ["pin"],
    "unpin_message": ["unpin"],
    "purge_messages": ["delete"],
    "delete_message": ["delete"],
    "toggle_setting": ["store"],
    "set_slowmode": ["set_slow_mode"],
    "show_admins": ["get_administrators"],
    "show_id": ["uid"],
    "show_info": ["get_chat"],
    "show_rules": ["store"],
    "set_rules": ["store.create"],
    "show_welcome": ["store"],
    "set_welcome": ["store.create"],
    "report_user": ["store.create"],
    "show_settings": ["store"],
    "show_stats": ["store"],
    "broadcast_message": ["send_message"],
}


def run_test():
    spec = group_management_spec()
    print(f"Spec: {spec.bot_name} with {len(spec.commands)} commands, {len(spec.entities)} entities")
    print(f"Commands: {spec.command_names()}")
    print()

    tmpdir = Path(tempfile.mkdtemp(prefix="test_group_mgmt_"))
    try:
        # Transpile
        files = transpile_spec(spec, tmpdir)
        print(f"Generated {len(files)} files: {files}")
        print()

        # Compile all .py files
        handlers_py = tmpdir / "app" / "handlers.py"
        if not handlers_py.exists():
            print("❌ FAIL: handlers.py not generated!")
            return False

        handlers_code = handlers_py.read_text(encoding="utf-8")

        # Compile handlers.py
        try:
            py_compile.compile(str(handlers_py), doraise=True)
            print("✅ handlers.py compiles successfully")
        except py_compile.PyCompileError as e:
            print(f"❌ FAIL: handlers.py does not compile: {e}")
            return False

        # Check each command has a handler function
        all_ok = True
        for cmd in spec.commands:
            fn_name = f"async def {cmd.name}_handler"
            if fn_name not in handlers_code:
                print(f"❌ FAIL: handler for /{cmd.name} not found in handlers.py")
                all_ok = False
            else:
                print(f"✅ Handler for /{cmd.name} found")

        print()

        # Check each action_type produces real API calls
        api_checks_passed = 0
        api_checks_failed = 0
        for cmd in spec.commands:
            if not cmd.action_type or cmd.action_type in ("", "none"):
                continue
            expected_calls = EXPECTED_API_CALLS.get(cmd.action_type, [])
            if not expected_calls:
                print(f"⚠️  No expected API calls defined for action_type={cmd.action_type}")
                continue

            # Find the handler function body
            fn_start = handlers_code.find(f"async def {cmd.name}_handler")
            if fn_start == -1:
                continue
            # Find the next function or end of file
            fn_end = handlers_code.find("async def ", fn_start + 10)
            if fn_end == -1:
                fn_end = len(handlers_code)
            handler_body = handlers_code[fn_start:fn_end]

            # Check each expected API call
            found_all = True
            for expected in expected_calls:
                if expected not in handler_body:
                    print(f"❌ /{cmd.name} (action_type={cmd.action_type}): missing API call '{expected}'")
                    found_all = False
                else:
                    pass  # Found it

            if found_all:
                print(f"✅ /{cmd.name} (action_type={cmd.action_type}): all expected API calls present")
                api_checks_passed += 1
            else:
                api_checks_failed += 1

        print()
        print(f"API call checks: {api_checks_passed} passed, {api_checks_failed} failed")

        # Compile all other .py files too
        compile_errors = []
        for py_file in tmpdir.rglob("*.py"):
            try:
                py_compile.compile(str(py_file), doraise=True)
            except py_compile.PyCompileError as e:
                compile_errors.append(f"{py_file.name}: {e}")

        if compile_errors:
            print(f"❌ Compile errors in other files:")
            for err in compile_errors[:5]:
                print(f"  {err}")
            all_ok = False
        else:
            print("✅ All .py files compile successfully")

        print()
        if all_ok and api_checks_failed == 0:
            print("=" * 60)
            print("ALL TESTS PASSED ✅")
            print("=" * 60)
            return True
        else:
            print("=" * 60)
            print("SOME TESTS FAILED ❌")
            print("=" * 60)
            return False

    except Exception as e:
        import traceback
        print(f"❌ EXCEPTION: {type(e).__name__}: {e}")
        traceback.print_exc()
        return False
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    success = run_test()
    sys.exit(0 if success else 1)
