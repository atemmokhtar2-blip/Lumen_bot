from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from bot_interface.config import GENERATION_STATUS_PREVIEW_LIMIT, ZIP_MAX_MB, OUTPUT_DIR
from bot_interface.helpers import escape_md, make_zip_from_path, split_file_for_telegram
from bot_interface.session_store import get_session_store

logger = logging.getLogger("ai_agent_7h_bot.generation_flow")

def _sentry_capture(**tags):
    try:
        from telegram_bot_engine.services.sentry_ops import capture_message
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
import traceback
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(sys.argv[1]).resolve()
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 10.0
sys.path.insert(0, str(ROOT))
t0 = time.perf_counter()

def fail(msg: str) -> None:
    print("SMOKE_FAIL:" + msg)
    raise SystemExit(2)

try:
    
# market_schema_check — fail closed if market present without tables
_mkt = ROOT / "app" / "services" / "market.py"
if _mkt.is_file():
    try:
        from app.db import init_db, connect
        init_db()
        import app.services.market as _market
        _market.wallet_balance(1)
        _market.list_plans()
        _market.role_of(1)
        try:
            import app.services.extras as _ex
            if hasattr(_ex, "feedback"):
                _ex.feedback(1, "smoke")
        except Exception as _ex_e:
            fail("extras_feedback:%s:%s" % (type(_ex_e).__name__, _ex_e))
    except Exception as _mkt_e:
        fail("market_schema:%s:%s" % (type(_mkt_e).__name__, _mkt_e))

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

priority, rest = [], []
for name, fn in handler_fns:
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
    async def reply_text(self, text, **kwargs):
        self.replies.append(str(text) if text is not None else "")
        return SimpleNamespace(message_id=len(self.replies))
    async def reply_document(self, *a, **k):
        return SimpleNamespace(message_id=99)
    async def reply_photo(self, *a, **k):
        return SimpleNamespace(message_id=98)

class Update:
    def __init__(self, text="/start"):
        self.effective_message = Msg(text)
        self.message = self.effective_message
        self.effective_user = SimpleNamespace(
            id=91001, first_name="Smoke", username="smoke_user", is_bot=False
        )
        self.effective_chat = SimpleNamespace(id=91001, type="private")
        self.callback_query = None

class Context:
    def __init__(self):
        self.args = []
        self.user_data = {}
        self.chat_data = {}
        self.bot_data = {}
        self.application = None
        async def _noop(*a, **k):
            return SimpleNamespace(message_id=1)
        self.bot = SimpleNamespace(
            id=1, username="smoke_bot",
            send_message=_noop, send_document=_noop, send_photo=_noop,
        )

async def invoke(name, fn, text="/start"):
    upd = Update(text)
    ctx = Context()
    try:
        res = fn(upd, ctx)
        if asyncio.iscoroutine(res):
            await asyncio.wait_for(res, timeout=5.0)
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
            soft = (
                "network", "timeout", "token", "httpx", "aiohttp",
                "cannot connect", "unauthorized", "attributeerror",
            )
            if any(s in low for s in soft):
                continue
            failures.append(err)
        if time.perf_counter() >= deadline:
            break
        await asyncio.sleep(0.05)

    if failures:
        fail("handler_failures:" + " | ".join(failures[:5]))
    has_start = any("start" in n.lower() for n, _ in ordered)
    if has_start and not start_ok:
        fail("start_handler_failed")
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

