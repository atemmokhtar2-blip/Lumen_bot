"""Configuration and environment loading for the Telegram bot interface."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("ai_agent_7h_bot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_USER_IDS = {
    int(x.strip())
    for x in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if x.strip().isdigit()
}
if not ALLOWED_USER_IDS:
    logger.warning(
        "ALLOWED_USER_IDS is empty — the bot will accept messages from ANY Telegram user. "
        "Set ALLOWED_USER_IDS in production for security."
    )

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/generated"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PORT = int(os.getenv("PORT", "8080"))
