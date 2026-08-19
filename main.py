"""
AI Agent 7h — Consumer Telegram bot + optional B2B API.

Modes:
  - Default: Telegram polling only (consumer product). B2B API is OFF.
  - ENABLE_API=1: also serves B2B HTTP API on PORT (generate/host/billing/dashboard)
  - python api_main.py: API-only process (explicit opt-in surface)
"""

from __future__ import annotations

# Observability — Sentry (strict: no-op without SENTRY_DSN)
try:
    from telegram_bot_engine.services.sentry_ops import init_sentry, capture_exception
    init_sentry(service="capability-maestro-telegram")
except Exception:
    def capture_exception(*_a, **_k):  # type: ignore
        return None


import asyncio
import multiprocessing
import os
import threading

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot_interface import (
    TELEGRAM_BOT_TOKEN,
    ALLOWED_USER_IDS,
    ALLOW_ALL_USERS,
    OUTPUT_DIR,
    PORT,
    logger,
    start_cmd,
    help_cmd,
    status_cmd,
    lang_cmd,
    handle_message,
    error_handler,
    start_health_server,
)
from bot_interface.commands import handle_non_text, unknown_cmd


def _start_b2b_api_process(port: int) -> None:
    """Run B2B API in a dedicated process (aiohttp needs main-thread signals otherwise).

    Any crash or unexpected exit ends the child with non-zero status so the
    parent watchdog fail-fasts the whole platform.
    """
    import sys
    try:
        from aiohttp import web
        from api.app import create_app

        app = create_app()
        print(f"[B2B API] listening on 0.0.0.0:{port}", flush=True)
        web.run_app(app, host="0.0.0.0", port=port, print=lambda *a, **k: None)
        print("[B2B API] run_app returned unexpectedly", flush=True)
        sys.exit(1)
    except SystemExit:
        raise
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _start_b2b_api_thread(port: int, death_event=None) -> None:
    """Fallback: AppRunner without signal handlers (safe inside a thread).

    On any unhandled failure, signal death_event and terminate the process
    (fail-fast): a platform without its API is partially down.
    """

    async def _serve() -> None:
        from aiohttp import web
        from api.app import create_app

        app = create_app()
        runner = web.AppRunner(app, handle_signals=False)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info("B2B API (thread/AppRunner) on 0.0.0.0:%s", port)
        while True:
            await asyncio.sleep(3600)

    try:
        asyncio.run(_serve())
        logger.error("B2B API thread exited cleanly unexpectedly — fail-fast")
    except Exception:
        logger.exception("B2B API thread failed — fail-fast")
    if death_event is not None:
        try:
            death_event.set()
        except Exception:
            pass
    # Hard stop: consumer bot alone is not a healthy ENABLE_API deployment
    os._exit(1)



def _cleanup_application(app) -> None:
    """Best-effort shutdown so restart cycles do not leak Application state."""
    if app is None:
        return
    try:
        import asyncio
        loop = None
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop = None
        except Exception:
            loop = None
        if loop is not None:
            try:
                loop.run_until_complete(app.shutdown())
            except Exception:
                pass
            try:
                loop.run_until_complete(app.updater.shutdown()) if getattr(app, "updater", None) else None
            except Exception:
                pass
    except Exception:
        pass
    try:
        del app
    except Exception:
        pass
    import gc
    gc.collect()

def main() -> None:
    if not TELEGRAM_BOT_TOKEN:
        logger.error(
            "TELEGRAM_BOT_TOKEN is not set. "
            "Set it in Railway Variables or a local .env file."
        )
        raise SystemExit(1)

    # ── Single poller only (prevents 409 Conflict on getUpdates) ──
    from bot_interface.singleton import acquire_bot_singleton, clear_telegram_webhook

    try:
        lock_path = acquire_bot_singleton(OUTPUT_DIR)
        logger.info("Polling singleton acquired (%s)", lock_path)
    except SystemExit as e:
        logger.error("%s", e)
        raise

    def _force_exclusive_polling(token: str) -> None:
        """Clear webhook twice with pause so no other getUpdates stays active."""
        clear_telegram_webhook(token)
        import time as _t
        _t.sleep(2.0)
        clear_telegram_webhook(token)
        _t.sleep(1.0)

    _force_exclusive_polling(TELEGRAM_BOT_TOKEN)
    logger.info("Telegram webhook cleared (exclusive polling mode)")

    logger.info("Starting AI Agent 7h Bot (consumer)...")
    allowed_repr = (
        sorted(ALLOWED_USER_IDS)
        if ALLOWED_USER_IDS
        else ("ALL (ALLOW_ALL_USERS=1)" if ALLOW_ALL_USERS else "NONE (safe default)")
    )
    logger.info(
        "OUTPUT_DIR=%s | ALLOWED_USER_IDS=%s | PORT=%s",
        OUTPUT_DIR,
        allowed_repr,
        PORT,
    )

    # Secure default: API is OFF unless operator explicitly enables it.
    # Running the consumer bot must not expose the B2B surface on 0.0.0.0.
    enable_api = (os.getenv("ENABLE_API") or "0").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    api_death = threading.Event()
    api_proc = None
    if enable_api:
        mode = (os.getenv("API_PROCESS_MODE") or "process").strip().lower()
        if mode in {"thread", "runner"}:
            # Non-daemon so a silent death is visible; death still triggers os._exit
            t = threading.Thread(
                target=_start_b2b_api_thread,
                args=(PORT, api_death),
                daemon=False,
                name="b2b-api",
            )
            t.start()
            logger.info("B2B API thread started on port %s (fail-fast on death)", PORT)
        else:
            api_proc = multiprocessing.Process(
                target=_start_b2b_api_process,
                args=(PORT,),
                daemon=False,
                name="b2b-api-process",
            )
            api_proc.start()
            logger.info("B2B API process started on port %s pid=%s", PORT, api_proc.pid)

        def _watch_api_worker() -> None:
            import time
            """Fail-fast if API process/thread dies while bot is still polling."""
            while True:
                if api_death.is_set():
                    logger.error("B2B API death_event set — stopping main process")
                    os._exit(1)
                if api_proc is not None and not api_proc.is_alive():
                    code = api_proc.exitcode
                    logger.error(
                        "B2B API process died (exitcode=%s) — stopping main process",
                        code,
                    )
                    os._exit(1 if code else 1)
                time.sleep(2.0)  # noqa: watchdog interval

        threading.Thread(
            target=_watch_api_worker, daemon=True, name="b2b-api-watchdog"
        ).start()
    else:
        threading.Thread(target=start_health_server, args=(PORT,), daemon=True).start()

    def _wire(application: Application) -> None:
        application.add_handler(CommandHandler("start", start_cmd))
        application.add_handler(CommandHandler("help", help_cmd))
        application.add_handler(CommandHandler("status", status_cmd))
        application.add_handler(CommandHandler("lang", lang_cmd))
        application.add_handler(CommandHandler("language", lang_cmd))
        # Never leave an unknown slash command without a Telegram response.
        application.add_handler(MessageHandler(filters.COMMAND, unknown_cmd))
        application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
        )
        application.add_handler(
            MessageHandler(
                ~filters.TEXT & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
                handle_non_text,
            )
        )
        application.add_error_handler(error_handler)

    # Retry loop: 409 Conflict during rolling deploy must NOT leave the bot dead.
    max_cycles = int(os.getenv("POLL_RESTART_MAX", "40") or "40")
    import time as _time

    app = None  # per-cycle; cleaned after each pass
    for cycle in range(1, max_cycles + 1):
        try:
            _force_exclusive_polling(TELEGRAM_BOT_TOKEN)
            # Always build a fresh Application — avoids "start_polling never awaited"
            # after a previous cycle stopped mid-flight.
            app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
            _wire(app)
            logger.info("Polling cycle %s/%s starting…", cycle, max_cycles)
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                bootstrap_retries=3,
                close_loop=False,
            )
            logger.warning(
                "run_polling returned (cycle=%s). Re-clearing webhook and restarting…",
                cycle,
            )
            _cleanup_application(app)
            app = None
        except SystemExit:
            raise
        except KeyboardInterrupt:
            raise
        except Exception as e:
            err = str(e)
            is_conflict = "Conflict" in type(e).__name__ or "Conflict" in err or "409" in err
            logger.error(
                "Polling exception (%s): %s — cycle %s/%s%s",
                type(e).__name__,
                err[:200],
                cycle,
                max_cycles,
                " [Telegram Conflict — another getUpdates active]" if is_conflict else "",
            )
            if is_conflict:
                # Longer pause so the other instance can die during rolling deploy
                _time.sleep(min(5.0 + cycle * 2.0, 30.0))
                try:
                    _cleanup_application(app)
                except Exception:
                    pass
                app = None
                _force_exclusive_polling(TELEGRAM_BOT_TOKEN)
                continue
        _time.sleep(min(2.0 + cycle, 12.0))
        _force_exclusive_polling(TELEGRAM_BOT_TOKEN)

    logger.error("Exhausted poll restart cycles — exiting")
    raise SystemExit(2)


if __name__ == "__main__":
    import os as _os
    if not (_os.getenv("TELEGRAM_BOT_TOKEN") or "").strip():
        raise SystemExit(
            "TELEGRAM_BOT_TOKEN is missing. Set it in Railway Variables, then redeploy."
        )
    # Required on some platforms for multiprocessing spawn
    multiprocessing.freeze_support()
    main()
