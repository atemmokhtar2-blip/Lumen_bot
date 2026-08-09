"""Configuration and environment loading for the Telegram bot interface."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root (next to main.py), then cwd as fallback
_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env")
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
# Safer default: empty ALLOWED_USER_IDS means DENY everyone unless explicitly
# ALLOW_ALL_USERS=1 (or true/yes/on). Prevents accidental open bots.
_ALLOW_ALL_RAW = (os.getenv("ALLOW_ALL_USERS") or "").strip().lower()
ALLOW_ALL_USERS = _ALLOW_ALL_RAW in {"1", "true", "yes", "on"}

if not ALLOWED_USER_IDS and not ALLOW_ALL_USERS:
    logger.critical(
        "ALLOWED_USER_IDS is empty and ALLOW_ALL_USERS is not enabled. "
        "No users will be able to use the bot. "
        "Set ALLOWED_USER_IDS=123,456 or ALLOW_ALL_USERS=1 (insecure)."
    )
elif not ALLOWED_USER_IDS and ALLOW_ALL_USERS:
    logger.warning(
        "ALLOW_ALL_USERS=1 — the bot accepts messages from ANY Telegram user. "
        "This is insecure for production. Prefer ALLOWED_USER_IDS."
    )

OUTPUT_DIR = Path(os.getenv("OUTPUT_DIR", "/tmp/generated"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
PORT = int(os.getenv("PORT", "8080"))
