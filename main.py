"""
Lumen — Consumer Telegram bot + optional B2B API.

Modes:
  - Default: Telegram polling only (consumer product). B2B API is OFF.
  - ENABLE_API=1: also serves B2B HTTP API on PORT (generate/host/billing/dashboard)
  - python api_main.py: API-only process (explicit opt-in surface)
"""

from __future__ import annotations

# Observability — Sentry (strict: no-op without SENTRY_DSN)
try:
    from lumen.engine.services.sentry_ops import init_sentry, capture_exception
    from lumen.identity import TELEGRAM_SERVICE_ID
    init_sentry(service=TELEGRAM_SERVICE_ID)
except Exception:
    def capture_exception(*_a, **_k):  # type: ignore
        return None


import asyncio
import multiprocessing
import os
import threading

# Dynamic secrets — memory store; scrub os.environ in production
try:
    from lumen.platform.secrets_provider import (
        assert_critical_secrets_present,
        assert_environ_scrubbed,
        install_secret_access_bridge,
        load_dotenv_if_dev,
        load_secrets,
    )
    load_dotenv_if_dev()
    load_secrets(only_missing=True)
    assert_critical_secrets_present()
    assert_environ_scrubbed()
    install_secret_access_bridge()
except Exception as _secrets_exc:
    import sys as _sys
    _sys.stderr.write("FATAL secrets boot: %s\n" % (_secrets_exc,))
    raise SystemExit(2) from _secrets_exc


from telegram import Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    PreCheckoutQueryHandler,
    filters,
)

from lumen.bot import (
    TELEGRAM_BOT_TOKEN,
    ALLOWED_USER_IDS,
    ALLOW_ALL_USERS,
    OUTPUT_DIR,
    PORT,
    logger,
    start_cmd,
    referral_cmd,
    help_cmd,
    status_cmd,
    lang_cmd,
    handle_message,
    error_handler,
    start_health_server,
)
from lumen.bot.commands import handle_non_text, unknown_cmd

# Redact secrets from all log records (not only user-facing errors)
try:
    from lumen.bot.sanitize import install_secret_log_filter
    install_secret_log_filter()
except Exception:
    pass



# Graceful shutdown coordination (API death → stop polling cleanly)
_shutdown_reason: str = ""
_shutdown_event = threading.Event()
_active_application = None  # set in main() so watchdog can stop polling


def _request_graceful_shutdown(reason: str) -> None:
    """Request process exit without os._exit — stop PTB application first."""
    global _shutdown_reason, _active_application
    _shutdown_reason = reason or "shutdown"
    _shutdown_event.set()
    app = _active_application
    if app is not None:
        try:
            app.stop()
        except Exception:
            logger.exception("application.stop during graceful shutdown failed")
        try:
            app.shutdown()
        except Exception:
            pass





def _install_signal_handlers() -> None:
    """SIGTERM/SIGINT → graceful stop of polling (no os._exit)."""
    import signal

    def _handler(signum, _frame):
        try:
            name = signal.Signals(signum).name
        except Exception:
            name = str(signum)
        logger.info("signal %s received — graceful shutdown", name)
        _request_graceful_shutdown(f"signal:{name}")

    for sig in (getattr(signal, "SIGTERM", None), getattr(signal, "SIGINT", None)):
        if sig is None:
            continue
        try:
            signal.signal(sig, _handler)
        except Exception:
            pass


def _start_b2b_api_process(port: int) -> None:
    """Run B2B API in a dedicated process (aiohttp needs main-thread signals otherwise).

    Any crash or unexpected exit ends the child with non-zero status so the
    parent watchdog fail-fasts the whole platform.
    """
    import sys
    try:
        from aiohttp import web
        from lumen.api.app import create_app

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
        from lumen.api.app import create_app

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
    # Graceful: signal death_event only; main loop stops polling and cleans up.
    # Avoid os._exit which can truncate in-flight work and corrupt SQLite/WAL.



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

    # Validate token is live before acquiring exclusive polling lease
    try:
        import urllib.request
        import json as _json

        _url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe"
        with urllib.request.urlopen(_url, timeout=15) as _resp:
            _body = _json.load(_resp)
        if not _body.get("ok") or not (_body.get("result") or {}).get("id"):
            logger.error("TELEGRAM_BOT_TOKEN rejected by Telegram getMe: %s", _body)
            raise SystemExit(1)
        _bot_username = (_body.get("result") or {}).get("username") or "?"
        logger.info("Telegram token valid — @%s", _bot_username)
    except SystemExit:
        raise
    except Exception as _tok_exc:
        logger.error("TELEGRAM_BOT_TOKEN validation failed: %s", _tok_exc)
        raise SystemExit(1)

    # Public mode without shared Redis rate limits = multi-worker cost DoS
    try:
        from lumen.platform.runtime_config import is_dev, redis_url

        if ALLOW_ALL_USERS and not redis_url() and not is_dev():
            logger.error(
                "ALLOW_ALL_USERS=1 requires REDIS_URL for shared rate limiting outside dev"
            )
            raise SystemExit(1)
    except SystemExit:
        raise
    except Exception:
        logger.exception("public-bot rate-limit precondition check failed")

    # ── Single poller only (prevents 409 Conflict on getUpdates) ──
    from lumen.bot.singleton import acquire_bot_singleton, clear_telegram_webhook

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

    logger.info("Starting Lumen (consumer)...")

    try:
        from lumen.engine.services.gemini_client import status_snapshot
        _gs = status_snapshot()
        logger.info(
            "Gemini status at boot: enabled=%s key_present=%s key_len=%s model=%s env_names=%s",
            _gs.get("enabled"),
            _gs.get("key_present"),
            _gs.get("key_len"),
            _gs.get("model"),
            _gs.get("env_names_seen"),
        )
        if not _gs.get("key_present"):
            logger.warning(
                "GEMINI_API_KEY not visible to this process — set on the same Railway service and redeploy"
            )
    except Exception:
        logger.exception("Gemini status probe failed at boot")

    # NOTE: A boot-time "enqueue pending resumes" call previously lived here
    # but referenced a module (lumen.engine.services.multi_agent.redis_board)
    # and function (enqueue_pending_resumes) that never existed in the
    # codebase — it always failed silently.  Cross-process HITL resume is now
    # handled durably by the SqliteSaver checkpoint (langgraph_pipeline.runner)
    # and resume_langgraph_hitl(), so the dead import has been removed.

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
            # Non-daemon so a silent death is visible; death triggers graceful shutdown
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
            # Immediate fail-fast if child dies during boot (port bind / create_app)
            import time as _boot_t
            _boot_t.sleep(0.5)
            if not api_proc.is_alive():
                logger.error(
                    "B2B API process died during startup (exitcode=%s) — aborting",
                    api_proc.exitcode,
                )
                raise SystemExit(1)

        def _watch_api_worker() -> None:
            import time
            """Fail-fast if API process/thread dies while bot is still polling."""
            while True:
                if api_death.is_set():
                    logger.error("B2B API death_event set — requesting graceful shutdown")
                    _request_graceful_shutdown("api_death_event")
                    return
                if api_proc is not None and not api_proc.is_alive():
                    code = api_proc.exitcode
                    logger.error(
                        "B2B API process died (exitcode=%s) — requesting graceful shutdown",
                        code,
                    )
                    _request_graceful_shutdown(f"api_proc_exit:{code}")
                    return
                time.sleep(2.0)  # noqa: watchdog interval

        threading.Thread(
            target=_watch_api_worker, daemon=True, name="b2b-api-watchdog"
        ).start()
    else:
        threading.Thread(target=start_health_server, args=(PORT,), daemon=True).start()

    def _wire(application: Application) -> None:
        application.add_handler(CommandHandler("start", start_cmd))
        application.add_handler(CommandHandler("referral", referral_cmd))
        application.add_handler(CommandHandler("help", help_cmd))
        application.add_handler(CommandHandler("status", status_cmd))
        application.add_handler(CommandHandler("lang", lang_cmd))
        application.add_handler(CommandHandler("language", lang_cmd))
        # Multi-conversation threads
        from lumen.bot.conversation_ui import (
            cmd_new_conversation,
            cmd_conversations,
            cmd_history,
            cmd_export,
            cmd_search,
            handle_conversation_callback,
        )
        application.add_handler(CommandHandler("new", cmd_new_conversation))
        application.add_handler(CommandHandler("conversations", cmd_conversations))
        application.add_handler(CommandHandler("history", cmd_history))
        application.add_handler(CommandHandler("export", cmd_export))
        application.add_handler(CommandHandler("search", cmd_search))
        application.add_handler(
            CallbackQueryHandler(handle_conversation_callback, pattern=r"^conv:")
        )
        # Engine UI callbacks (Batch 0 foundation — lumen:ui:*)
        from lumen.bot.ui.callback_router import handle_ui_callback
        # L2. = HMAC-signed callbacks; lumen:ui: = legacy (ignored by decoder)
        application.add_handler(
            CallbackQueryHandler(handle_ui_callback, pattern=r"^(L2\.|lumen:ui:)")
        )
        # Telegram Stars (XTR) payment handlers — in-Telegram Pro plan checkout
        from lumen.bot.ui.payment_handlers import (
            handle_pre_checkout,
            handle_successful_payment,
        )
        application.add_handler(PreCheckoutQueryHandler(handle_pre_checkout))
        application.add_handler(
            MessageHandler(filters.SUCCESSFUL_PAYMENT, handle_successful_payment)
        )
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
            try:
                from telegram.request import HTTPXRequest
                _tg_request = HTTPXRequest(
                    connect_timeout=15.0,
                    read_timeout=40.0,
                    write_timeout=40.0,
                    pool_timeout=15.0,
                )
                async def _post_init(application):
                    try:
                        from lumen.bot.ui.menu_button import configure_menu_button
                        ok = await configure_menu_button(application.bot, chat_id=None)
                        logger.info("default MenuButtonWebApp configured=%s", ok)
                    except Exception:
                        logger.exception("post_init menu button failed")

                # Official PTB persistence → Redis (restart + multi-worker safe user_data)
                # Fail closed: without Redis, context loss is guaranteed on restart.
                from lumen.bot.ptb_redis_persistence import RedisPersistence
                _persistence = RedisPersistence(update_interval=1.0)
                logger.info(
                    "PTB RedisPersistence attached backend=%s update_interval=1s",
                    getattr(getattr(_persistence, "_store", None), "backend", "?"),
                )

                app = (
                    Application.builder()
                    .token(TELEGRAM_BOT_TOKEN)
                    .request(_tg_request)
                    .concurrent_updates(True)
                    .post_init(_post_init)
                    .persistence(_persistence)
                    .build()
                )
            except Exception:
                # Last-resort builder: still require persistence (no silent RAM-only)
                try:
                    from lumen.bot.ptb_redis_persistence import RedisPersistence
                    _persistence = RedisPersistence(update_interval=1.0)
                    app = (
                        Application.builder()
                        .token(TELEGRAM_BOT_TOKEN)
                        .persistence(_persistence)
                        .build()
                    )
                    logger.warning("Application built via fallback path WITH RedisPersistence")
                except Exception:
                    logger.exception(
                        "FATAL: cannot attach RedisPersistence — refusing silent RAM-only mode"
                    )
                    raise
            _wire(app)
            global _active_application
            _active_application = app
            logger.info("Polling cycle %s/%s starting…", cycle, max_cycles)
            if _shutdown_event.is_set():
                logger.error("Shutdown already requested (%s) — not starting polling", _shutdown_reason)
                break
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=False,
                bootstrap_retries=3,
                close_loop=False,
            )
            logger.warning(
                "run_polling returned (cycle=%s). Re-clearing webhook and restarting…",
                cycle,
            )
            _cleanup_application(app)
            app = None
            _active_application = None
            if _shutdown_event.is_set():
                logger.error("Graceful shutdown complete (%s)", _shutdown_reason)
                raise SystemExit(1)
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
