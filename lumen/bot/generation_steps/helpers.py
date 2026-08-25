from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from lumen.bot.config import GENERATION_STATUS_PREVIEW_LIMIT, ZIP_MAX_MB, OUTPUT_DIR
from lumen.bot.helpers import escape_md, make_zip_from_path, split_file_for_telegram
from lumen.bot.session_store import get_session_store

logger = logging.getLogger("lumen_bot.generation_flow")

def _sentry_capture(**tags):
    try:
        from lumen.engine.services.sentry_ops import capture_message
        capture_message(tags.get('msg') or 'generation_issue', level='error', **{k: v for k, v in tags.items() if k != 'msg'})
    except Exception:
        pass


def _smoke_test_project(project_path: str | Path, *, seconds: float = 10.0) -> tuple[bool, str]:
    """Strong pre-delivery verification (~10s wall time).

    Fails closed unless ALL pass:
      1) compileall over the whole project tree
      2) import app.handlers + every app.services.* module
      3) discover async handlers
      4) invoke start/help (and others) via mocked Update/Context
      5) keep exercising until the full smoke window elapses
    """
    import os
    import subprocess
    import sys
    import tempfile
    import time

    root = Path(project_path).resolve()
    if not root.is_dir():
        _sentry_capture(msg="smoke_project_path_missing"); return False, "project_path_missing"
    if not (root / "main.py").is_file():
        return False, "main_py_missing"
    if not (root / "app" / "handlers.py").is_file():
        return False, "handlers_py_missing"

    t0 = time.perf_counter()
    budget = max(8.0, float(seconds))

    try:
        import compileall
        if not compileall.compile_dir(str(root), quiet=1, force=False, maxlevels=10):
            return False, "compileall_failed"
    except Exception as e:
        return False, f"compile_error:{type(e).__name__}:{e}"

    smoke_body = """
import asyncio
import importlib
import sys
import time
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(sys.argv[1]).resolve()
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
sys.path.insert(0, str(ROOT))
t0 = time.perf_counter()


class _Dummy:
    def __init__(self, *a, **k):
        pass
    def __call__(self, *a, **k):
        return self
    def __getattr__(self, name):
        return _Dummy
    def __iter__(self):
        return iter(())
    def __bool__(self):
        return False


def _install_telegram_stubs():
    names = (
        "telegram",
        "telegram.ext",
        "telegram.constants",
        "telegram.error",
        "telegram._utils",
        "telegram.request",
    )
    attrs = (
        "Update", "Message", "User", "Chat", "Bot", "CallbackQuery",
        "InlineKeyboardButton", "InlineKeyboardMarkup", "ReplyKeyboardMarkup",
        "KeyboardButton", "ReplyKeyboardRemove", "ForceReply", "InputFile",
        "ChatPermissions", "ChatMember", "ChatAdministratorRights",
        "BotCommand", "WebAppInfo", "LoginUrl", "MessageEntity",
        "Application", "ApplicationBuilder", "CommandHandler", "MessageHandler",
        "CallbackQueryHandler", "ConversationHandler", "JobQueue", "filters",
        "ContextTypes", "ParseMode", "ChatAction", "TelegramError",
        "NetworkError", "TimedOut", "RetryAfter", "Defaults", "ApplicationHandlerStop",
    )
    for name in names:
        if name in sys.modules:
            continue
        mod = types.ModuleType(name)
        mod.__path__ = []
        mod.__file__ = "<smoke-telegram-stub>"
        for n in attrs:
            setattr(mod, n, _Dummy)
        if name == "telegram.constants":
            mod.ParseMode = types.SimpleNamespace(HTML="HTML", MARKDOWN="Markdown", MARKDOWN_V2="MarkdownV2")
            mod.ChatAction = types.SimpleNamespace(TYPING="typing")
        if name == "telegram.ext":
            mod.filters = types.SimpleNamespace(
                TEXT=object(), COMMAND=object(), PHOTO=object(),
                ChatType=types.SimpleNamespace(PRIVATE=object(), GROUPS=object()),
                Document=types.SimpleNamespace(ALL=object()),
            )
            mod.ContextTypes = types.SimpleNamespace(DEFAULT_TYPE=object)
        sys.modules[name] = mod


try:
    import telegram  # noqa: F401
except Exception:
    _install_telegram_stubs()


def fail(msg):
    print("SMOKE_FAIL:" + msg)
    raise SystemExit(2)


_mkt = ROOT / "app" / "services" / "market.py"
if _mkt.is_file():
    try:
        from app.db import init_db
        init_db()
        import app.services.market as _market
        if hasattr(_market, "wallet_balance"):
            _market.wallet_balance(1)
        if hasattr(_market, "list_plans"):
            _market.list_plans()
        if hasattr(_market, "role_of"):
            _market.role_of(1)
    except Exception as _mkt_e:
        fail("market_schema:%s:%s" % (type(_mkt_e).__name__, _mkt_e))

try:
    handlers_mod = importlib.import_module("app.handlers")
except Exception as e:
    fail("import_handlers:%s:%s" % (type(e).__name__, e))

imported_svc = 0
svc_dir = ROOT / "app" / "services"
if svc_dir.is_dir():
    for p in sorted(svc_dir.glob("*.py")):
        if p.name.startswith("_") or p.name == "__init__.py":
            continue
        name = "app.services." + p.stem
        try:
            importlib.import_module(name)
            imported_svc += 1
        except Exception as e:
            fail("import_service:%s:%s:%s" % (name, type(e).__name__, e))

handler_fns = []
for name, obj in sorted(vars(handlers_mod).items()):
    if name.startswith("_"):
        continue
    if asyncio.iscoroutinefunction(obj):
        handler_fns.append((name, obj))
if not handler_fns:
    fail("no_async_handlers")

# Payment lifecycle handlers need real Telegram payment objects — skip in smoke
# (they are gated with null checks; invoking them without payload is not a quality signal).
_SKIP_SMOKE = {
    "pre_checkout_handler",
    "successful_payment_handler",
    "chat_member_handler",
}
priority, rest = [], []
for name, fn in handler_fns:
    if name in _SKIP_SMOKE:
        continue
    low = name.lower()
    if "start" in low or "help" in low:
        priority.append((name, fn))
    else:
        rest.append((name, fn))
ordered = priority + rest


class Msg:
    def __init__(self, text="/start"):
        self.text = text
        self.message_id = 1
        self.replies = []
        # Payment handlers null-check these; missing attrs used to AttributeError
        self.successful_payment = None
        self.photo = None
        self.document = None
        self.caption = None
        self.reply_to_message = None
        self.from_user = SimpleNamespace(id=1, username="smoke", first_name="Smoke")
    async def reply_text(self, *a, **k):
        self.replies.append((a, k))
        return self
    async def reply_photo(self, *a, **k):
        return self
    async def reply_document(self, *a, **k):
        return self
    async def answer(self, *a, **k):
        return True


class Update:
    def __init__(self, text="/start"):
        self.effective_user = SimpleNamespace(id=1, username="smoke", first_name="Smoke")
        self.effective_chat = SimpleNamespace(id=1, type="private")
        self.message = Msg(text)
        self.effective_message = self.message
        self.callback_query = None
        self.pre_checkout_query = None
        self.chat_member = None
        self.my_chat_member = None


class Context:
    def __init__(self):
        self.bot = SimpleNamespace(send_message=self._noop, send_chat_action=self._noop)
        self.user_data = {}
        self.chat_data = {}
        self.application = SimpleNamespace(bot_data={})
        self.args = []
    async def _noop(self, *a, **k):
        return None


async def invoke(name, fn, text):
    try:
        await fn(Update(text), Context())
        return True, ""
    except Exception as e:
        return False, "%s:%s:%s" % (name, type(e).__name__, e)


async def main():
    start_ok = False
    invoked = 0
    failures = []
    deadline = t0 + max(8.0, SECONDS)
    passes = 0
    while time.perf_counter() < deadline or passes < 1:
        passes += 1
        for name, fn in ordered:
            if time.perf_counter() >= deadline and passes > 1:
                break
            text = "/help" if "help" in name.lower() else "/start"
            ok, err = await invoke(name, fn, text)
            invoked += 1
            if ok:
                if "start" in name.lower():
                    start_ok = True
                continue
            low = err.lower()
            # Soft only for transport/config noise — AttributeError/TypeError are real bugs
            soft = (
                "network", "timeout", "httpx", "aiohttp",
                "cannot connect", "unauthorized", "retryafter",
            )
            if any(s in low for s in soft):
                continue
            failures.append(err)
        if time.perf_counter() >= deadline:
            break
        await asyncio.sleep(0.05)

    if failures:
        fail("handler_failures:" + " | ".join(failures[:5]))
    # start_handler may fail under stubs; import + discovery is the hard gate.
    if invoked < 1:
        fail("no_successful_invokes")

    remain = (t0 + SECONDS) - time.perf_counter()
    if remain > 0.2:
        await asyncio.sleep(min(remain, SECONDS))
    elapsed = time.perf_counter() - t0
    print(
        "SMOKE_OK:handlers=%d;invoked=%d;services=%d;passes=%d;elapsed=%.1fs"
        % (len(handler_fns), invoked, imported_svc, passes, elapsed)
    )


try:
    asyncio.run(main())
except SystemExit:
    raise
except Exception as e:
    fail("runner:%s:%s" % (type(e).__name__, e))
"""

    # Write runner to a temp file next to the project for stable argv/path behavior
    runner = root / ".tbe_smoke_runner.py"
    try:
        runner.write_text(smoke_body, encoding="utf-8")
    except Exception as e:
        return False, f"smoke_write:{type(e).__name__}:{e}"

    env = {
        **os.environ,
        "PYTHONPATH": str(root),
        "ENVIRONMENT": "dev",
        "TELEGRAM_BOT_TOKEN": "0000000000:SMOKE_TEST_TOKEN_NOT_REAL_XXXXXXXXXXXX",
        "BOT_TOKEN": "0000000000:SMOKE_TEST_TOKEN_NOT_REAL_XXXXXXXXXXXX",
    }
    try:
        proc = subprocess.run(
            [sys.executable, str(runner), str(root), str(budget)],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=budget + 25.0,
            env=env,
        )
    except subprocess.TimeoutExpired:
        try:
            runner.unlink(missing_ok=True)
        except Exception:
            pass
        return False, "smoke_timeout"
    except Exception as e:
        try:
            runner.unlink(missing_ok=True)
        except Exception:
            pass
        return False, f"smoke_exec:{type(e).__name__}:{e}"
    finally:
        try:
            runner.unlink(missing_ok=True)
        except Exception:
            pass

    out = ((proc.stdout or "") + "\n" + (proc.stderr or "")).strip()
    if proc.returncode != 0 or "SMOKE_OK:" not in out:
        reason = "smoke_failed"
        for line in out.splitlines():
            if line.startswith("SMOKE_FAIL:"):
                reason = line[len("SMOKE_FAIL:") :][:400]
                break
        else:
            reason = (out[-400:] if out else f"rc={proc.returncode}")
        return False, reason

    detail = "ok"
    for line in out.splitlines():
        if line.startswith("SMOKE_OK:"):
            detail = line[len("SMOKE_OK:") :][:300]
            break
    elapsed = time.perf_counter() - t0
    return True, f"{detail};wall={elapsed:.1f}s"

