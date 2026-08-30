"""Configuration and environment loading for the Telegram bot interface."""

from __future__ import annotations

import logging
import os
from pathlib import Path

# Filesystem .env is DEV-ONLY. Production must use Doppler/Vault/AWS/GCP.
try:
    from lumen.platform.secrets_provider import load_dotenv_if_dev, load_secrets_into_environ
    load_dotenv_if_dev()
    load_secrets_into_environ(only_missing=True)
except Exception as _sec_exc:
    import logging as _logging
    _logging.getLogger("lumen_bot").error(
        "secrets_boot_failed: %s", type(_sec_exc).__name__
    )
    # Re-raise in production so we never run with a silent empty secret set
    try:
        from lumen.platform.secrets_provider import is_production
        if is_production():
            raise
    except Exception:
        raise

try:
    from lumen.platform.observability import setup_observability
    setup_observability(service_name=os.getenv("OTEL_SERVICE_NAME") or "lumen-telegram")
except Exception:
    logging.basicConfig(
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        level=logging.INFO,
    )
logger = logging.getLogger("lumen_bot")
try:
    from lumen.bot.sanitize import install_secret_log_filter
    install_secret_log_filter()
except Exception:
    pass

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_USER_IDS = {
    int(x.strip())
    for x in os.getenv("ALLOWED_USER_IDS", "").split(",")
    if x.strip().isdigit()
}

# Telegram access control — secure-by-default.
# Open public mode ONLY with explicit ALLOW_ALL_USERS=1.
# To lock: LOCK_BOT_TO_ALLOWLIST=1 + ALLOWED_USER_IDS=1,2,3
# Closed default: refuse strangers (prevents API-credit drain bots).
_LOCK_RAW = (os.getenv("LOCK_BOT_TO_ALLOWLIST") or "").strip().lower()
LOCK_BOT_TO_ALLOWLIST = _LOCK_RAW in {"1", "true", "yes", "on"}

_ALLOW_ALL_RAW = (os.getenv("ALLOW_ALL_USERS") or "").strip().lower()

if _ALLOW_ALL_RAW in {"1", "true", "yes", "on"}:
    ALLOW_ALL_USERS = True
elif _ALLOW_ALL_RAW in {"0", "false", "no", "off"}:
    ALLOW_ALL_USERS = False
elif LOCK_BOT_TO_ALLOWLIST and ALLOWED_USER_IDS:
    ALLOW_ALL_USERS = False
elif ALLOWED_USER_IDS:
    # Explicit allowlist without LOCK still means restricted mode
    ALLOW_ALL_USERS = False
else:
    # Secure default: CLOSED unless operator explicitly opens the bot
    ALLOW_ALL_USERS = False

if LOCK_BOT_TO_ALLOWLIST and ALLOWED_USER_IDS:
    logger.info(
        "Bot locked to ALLOWED_USER_IDS (%s users).",
        len(ALLOWED_USER_IDS),
    )
elif not ALLOW_ALL_USERS and not ALLOWED_USER_IDS:
    logger.warning(
        "Bot access CLOSED by default. "
        "Set ALLOW_ALL_USERS=1 (public) or ALLOWED_USER_IDS=… to accept users."
    )
elif not ALLOW_ALL_USERS and ALLOWED_USER_IDS:
    logger.info(
        "Bot restricted to ALLOWED_USER_IDS (%s users).",
        len(ALLOWED_USER_IDS),
    )
else:
    logger.warning(
        "Public Telegram bot mode ENABLED (ALLOW_ALL_USERS=1) — "
        "credits + rate limits are the only cost controls."
    )

def _resolve_output_dir() -> Path:
    candidates: list[Path] = []
    env = (os.getenv("OUTPUT_DIR") or "").strip()
    if env:
        candidates.append(Path(env).expanduser())
    try:
        from lumen.platform.paths import default_output_dir
        candidates.append(Path(default_output_dir()))
    except Exception:
        pass
    candidates.extend(
        [
            Path.home() / ".lumen",
            Path("/tmp") / "lumen_output",
            Path(__file__).resolve().parent.parent / ".runtime",
        ]
    )
    last_err: Exception | None = None
    for cand in candidates:
        try:
            cand.mkdir(parents=True, exist_ok=True)
            probe = cand / ".write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return cand.resolve()
        except Exception as exc:
            last_err = exc
            continue
    raise RuntimeError(f"no_writable_OUTPUT_DIR:{last_err}")


OUTPUT_DIR = _resolve_output_dir()
PORT = int(os.getenv("PORT", "8080"))


# ── Tunables (env-overridable, no magic numbers in handlers) ──────────
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE") or "12")
RATE_LIMIT_WINDOW_SECONDS = float(os.getenv("RATE_LIMIT_WINDOW_SECONDS") or "60")
LIVE_RUN_SECONDS = float(os.getenv("LIVE_RUN_SECONDS") or "900")
GENERATION_STATUS_PREVIEW_LIMIT = int(os.getenv("GENERATION_STATUS_PREVIEW_LIMIT") or "3500")
ZIP_MAX_MB = float(os.getenv("ZIP_MAX_MB") or "48")
