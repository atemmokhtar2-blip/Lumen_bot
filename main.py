"""
AI Agent 7h — Consumer Telegram bot + optional B2B API.

Modes:
  - Default: Telegram polling (consumer product)
  - ENABLE_API=1: also serves B2B HTTP API on PORT (generate/host/billing/dashboard)
  - python api_main.py: API-only process
"""

from __future__ import annotations

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
from bot_interface.commands import handle_non_text


def _start_b2b_api_process(port: int) -> None:
    """Run B2B API in a dedicated process (aiohttp needs main-thread signals otherwise)."""
    from aiohttp import web
    from api.app import create_app

    app = create_app()
    print(f"[B2B API] listening on 0.0.0.0:{port}", flush=True)
    web.run_app(app, host="0.0.0.0", port=port, print=lambda *a, **k: None)


def _start_b2b_api_thread(port: int) -> None:
    """Fallback: AppRunner without signal handlers (safe inside a thread)."""

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
    except Exception:
        logger.exception("B2B API thread failed")


def main() -> None:
    # Optional one-shot Rasa train (never crash the bot if train/pip fails)
    try:
        import runpy
        from pathlib import Path as _P
        runpy.run_path(
            str(_P(__file__).resolve().parent / "scripts" / "ensure_dialogue_model.py"),
            run_name="ensure_dialogue_model",
        )
    except SystemExit:
        pass
    except Exception:
        pass

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

    # Clear any leftover webhook so polling is exclusive
    if clear_telegram_webhook(TELEGRAM_BOT_TOKEN):
        logger.info("Telegram webhook cleared (polling mode)")
    else:
        logger.warning("Could not clear webhook (continuing; may still work)")

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

    enable_api = (os.getenv("ENABLE_API") or "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    if enable_api:
        mode = (os.getenv("API_PROCESS_MODE") or "process").strip().lower()
        if mode in {"thread", "runner"}:
            threading.Thread(
                target=_start_b2b_api_thread, args=(PORT,), daemon=True, name="b2b-api"
            ).start()
        else:
            # Default: separate process — avoids set_wakeup_fd / signal errors
            multiprocessing.Process(
                target=_start_b2b_api_process,
                args=(PORT,),
                daemon=True,
                name="b2b-api-process",
            ).start()
            logger.info("B2B API process started on port %s", PORT)
    else:
        threading.Thread(target=start_health_server, args=(PORT,), daemon=True).start()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CommandHandler("language", lang_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(
        MessageHandler(
            ~filters.TEXT & ~filters.COMMAND & ~filters.StatusUpdate.ALL,
            handle_non_text,
        )
    )
    app.add_error_handler(error_handler)

    logger.info("Telegram bot is running (polling)...")

    def _wire(application: Application) -> None:
        application.add_handler(CommandHandler("start", start_cmd))
        application.add_handler(CommandHandler("help", help_cmd))
        application.add_handler(CommandHandler("status", status_cmd))
        application.add_handler(CommandHandler("lang", lang_cmd))
        application.add_handler(CommandHandler("language", lang_cmd))
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
    # PTB often stops the Application on Conflict without raising to main().
    max_cycles = int(os.getenv("POLL_RESTART_MAX", "30") or "30")
    import time as _time

    for cycle in range(1, max_cycles + 1):
        try:
            clear_telegram_webhook(TELEGRAM_BOT_TOKEN)
            if cycle > 1:
                app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
                _wire(app)
            logger.info("Polling cycle %s/%s starting…", cycle, max_cycles)
            app.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
            )
            # run_polling returned — usually Conflict/stop, not a clean SIGTERM
            logger.warning(
                "run_polling returned (cycle=%s). Re-clearing webhook and restarting…",
                cycle,
            )
        except SystemExit:
            raise
        except KeyboardInterrupt:
            raise
        except Exception as e:
            logger.error(
                "Polling exception (%s): %s — cycle %s/%s",
                type(e).__name__,
                str(e)[:200],
                cycle,
                max_cycles,
            )
        _time.sleep(min(2.0 + cycle, 12.0))
        clear_telegram_webhook(TELEGRAM_BOT_TOKEN)

    logger.error("Exhausted poll restart cycles — exiting")
    raise SystemExit(2)


if __name__ == "__main__":
    # Required on some platforms for multiprocessing spawn
    multiprocessing.freeze_support()
    main()
