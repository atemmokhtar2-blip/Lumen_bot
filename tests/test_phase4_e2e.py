"""Phase 4 — generation quality, anti-template, command handler smoke."""
from __future__ import annotations

import asyncio
import re
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import os
pytestmark = pytest.mark.skipif(
    not (os.getenv("GROQ_API_KEY") or os.getenv("HF_TOKEN")),
    reason="SpecTranslator requires GROQ_API_KEY or HF_TOKEN",
)

from telegram_bot_engine import generate_bot
from telegram_bot_engine.formal_engine.verification.quality import measure_quality

SPEC = """
اعمل بوت تليجرام باسم Phase4Ops.
الأوامر:
/start - ترحيب
/help - مساعدة
/register - تسجيل مستخدم
/new_task - إنشاء مهمة
/my_tasks - عرض مهامي
/complete_task - إكمال مهمة
/ban - حظر مستخدم
الكيانات:
- User (id, name, banned)
- Task (id, title, status, owner_id)
"""

EXPECTED_CMDS = [
    "start", "help", "register", "new_task", "my_tasks", "complete_task", "ban",
]
EXPECTED_ENTS = ["User", "Task"]
FORBIDDEN = [
    "list_mine", "show_categories", "class Order", "show_products",
    "FoodOrder", "SpaBooking", "PlaceOrder",
]


def _make_update(text: str = "/start"):
    update = MagicMock()
    update.effective_user = MagicMock(id=42, full_name="Tester", username="tester")
    update.effective_chat = MagicMock(id=99)
    msg = MagicMock()
    msg.text = text
    msg.chat_id = 99
    msg.reply_text = AsyncMock(return_value=MagicMock())
    update.message = msg
    update.effective_message = msg
    update.callback_query = None
    return update


def _make_context(args=None):
    ctx = MagicMock()
    ctx.args = args or []
    ctx.user_data = {}
    ctx.application = MagicMock()
    ctx.application.bot_data = {}
    ctx.bot = MagicMock()
    ctx.bot.send_message = AsyncMock()
    return ctx


async def _run_all_handlers(root: Path) -> dict:
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app.") or mod in ("main", "config"):
            del sys.modules[mod]
    sys.path.insert(0, str(root))
    out: dict = {}
    try:
        import app.handlers as H  # type: ignore
        pairs = dict(
            re.findall(
                r"CommandHandler\(\s*['\"](\w+)['\"]\s*,\s*(\w+)",
                (root / "main.py").read_text(encoding="utf-8"),
            )
        )
        for cmd in EXPECTED_CMDS:
            fn = getattr(H, pairs.get(cmd, ""), None)
            if not fn:
                out[cmd] = {"ok": False, "error": "MISSING"}
                continue
            upd, ctx = _make_update(f"/{cmd}"), _make_context(["1"] if cmd == "ban" else [])
            try:
                await fn(upd, ctx)
                out[cmd] = {
                    "ok": True,
                    "replies": upd.effective_message.reply_text.await_count,
                }
            except Exception as e:
                out[cmd] = {"ok": False, "error": f"{type(e).__name__}:{e}"[:160]}
    except Exception as e:
        out["_import"] = str(e)[:200]
    finally:
        if str(root) in sys.path:
            sys.path.remove(str(root))
    return out


def test_phase4_e2e_generation_and_commands():
    work = tempfile.mkdtemp(prefix="phase4_test_")
    result = generate_bot(SPEC, work_dir=work)
    assert result.success, result.errors
    root = Path(result.project_path)
    assert (root / "main.py").exists()

    cmds = re.findall(
        r"CommandHandler\(['\"](\w+)",
        (root / "main.py").read_text(encoding="utf-8"),
    )
    assert cmds == EXPECTED_CMDS

    models = re.findall(
        r"^class\s+(\w+)",
        (root / "app" / "models.py").read_text(encoding="utf-8"),
        re.M,
    )
    assert set(models) == set(EXPECTED_ENTS)

    # Absolute ban on domain template strings in generated project
    hits = []
    for p in root.rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        for bad in FORBIDDEN:
            if bad in text:
                hits.append(f"{p.name}:{bad}")
    assert hits == [], hits

    q = measure_quality(
        root,
        expected_commands=EXPECTED_CMDS,
        expected_entities=EXPECTED_ENTS,
        structure_gate_ok=True,
        code_engine_ok=True,
        verify_ok=True,
        compile_ok=True,
    )
    assert q.ok and q.score >= 0.9, q.to_dict()
    assert not q.metrics.get("invented_commands")
    assert not q.metrics.get("invented_entities")

    hr = asyncio.run(_run_all_handlers(root))
    assert "_import" not in hr, hr
    for cmd in EXPECTED_CMDS:
        assert hr[cmd].get("ok"), (cmd, hr[cmd])
        assert hr[cmd].get("replies", 0) >= 1, (cmd, hr[cmd])
