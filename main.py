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

    # Railway / multi-replica: only replica 0 may poll Telegram
    replica = (
        os.getenv("RAILWAY_REPLICA_ID")
        or os.getenv("RAILWAY_REPLICA")
        or os.getenv("REPLICA_ID")
        or "0"
    ).strip()
    if replica not in {"0", ""}:
        logger.error(
            "Non-primary replica (id=%s) — skipping Telegram polling. "
            "Set service replicas=1 on Railway.",
            replica,
        )
        # Keep process alive for health if needed
        if (os.getenv("ENABLE_API") or "1").strip().lower() not in {"0", "false", "no", "off"}:
            _start_b2b_api_process(PORT)
        else:
            start_health_server(PORT)
        return

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

    # Confirm dialogue model is on disk (Rasa path)
    try:
        from pathlib import Path as _Path
        _models = list((_Path(__file__).resolve().parent / "dialogue" / "models").glob("*.tar.gz"))
        if _models:
            logger.info("Dialogue model ready: %s (%.1f MB)", _models[0].name, _models[0].stat().st_size / 1e6)
        else:
            logger.warning("No dialogue/models/*.tar.gz — DIALOGUE_ENABLED will be inert until model ships")
    except Exception:
        pass

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
            multiprocessing.Process(
                target=_start_b2b_api_process,
                args=(PORT,),
                daemon=True,
                name="b2b-api-process",
            ).start()
            logger.info("B2B API process started on port %s", PORT)
    else:
        threading.Thread(target=start_health_server, args=(PORT,), daemon=True).start()

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
    max_cycles = int(os.getenv("POLL_RESTART_MAX", "40") or "40")
    import time as _time

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
                _force_exclusive_polling(TELEGRAM_BOT_TOKEN)
                continue
        _time.sleep(min(2.0 + cycle, 12.0))
        _force_exclusive_polling(TELEGRAM_BOT_TOKEN)

    logger.error("Exhausted poll restart cycles — exiting")
    raise SystemExit(2)


if __name__ == "__main__":
    # Required on some platforms for multiprocessing spawn
    multiprocessing.freeze_support()
    main()
