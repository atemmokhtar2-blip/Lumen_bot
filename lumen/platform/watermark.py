"""Inject plan watermark into generated bot projects (Explorer tier)."""
from __future__ import annotations

import logging
import re
from pathlib import Path

from .plans import WATERMARK_TEXT

logger = logging.getLogger(__name__)

_SNIPPET = f'''
# --- Lumen plan watermark (do not remove) ---
try:
    from telegram.ext import ApplicationHandlerStop
except Exception:
    ApplicationHandlerStop = Exception  # type: ignore

async def _lumen_watermark_start(update, context):
    """Append platform watermark on /start for free Explorer plan builds."""
    try:
        msg = update.effective_message
        if msg is not None:
            await msg.reply_text("{WATERMARK_TEXT}")
    except Exception:
        pass

def _lumen_register_watermark(app):
    try:
        from telegram.ext import CommandHandler
        app.add_handler(CommandHandler("start", _lumen_watermark_start), group=99)
    except Exception:
        pass
# --- end watermark ---
'''


def inject_watermark(project_path: str | Path) -> bool:
    """Best-effort inject watermark into main.py / bot entry. Returns True if applied."""
    root = Path(project_path)
    if not root.is_dir():
        return False
    candidates = [
        root / "main.py",
        root / "bot.py",
        root / "app.py",
    ]
    # also search one level
    for p in root.glob("*.py"):
        if p.name not in {c.name for c in candidates}:
            candidates.append(p)

    target = None
    text = ""
    for c in candidates:
        if not c.is_file():
            continue
        try:
            raw = c.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if "Application.builder" in raw or "ApplicationBuilder" in raw or "CommandHandler" in raw:
            target = c
            text = raw
            break
    if target is None:
        # still stamp a watermark.txt so package shows it
        try:
            (root / "POWERED_BY_LUMEN.txt").write_text(WATERMARK_TEXT + "\n", encoding="utf-8")
            return True
        except Exception:
            return False

    if "lumen_watermark" in text or WATERMARK_TEXT in text:
        return True

    # Append snippet + try to hook after app build
    new = text
    if "_lumen_register_watermark" not in new:
        new = new.rstrip() + "\n" + _SNIPPET + "\n"
    # Hook: after app = Application.builder()...build()
    patterns = [
        (r"(app\s*=\s*Application\.builder\(\)[\s\S]*?\.build\(\))", r"\1\n_lumen_register_watermark(app)"),
        (r"(application\s*=\s*Application\.builder\(\)[\s\S]*?\.build\(\))", r"\1\n_lumen_register_watermark(application)"),
    ]
    hooked = False
    for pat, repl in patterns:
        if re.search(pat, new):
            new = re.sub(pat, repl, new, count=1)
            hooked = True
            break
    if not hooked:
        # fallback footer note in start handler text if any
        new = new.replace(
            'await update.message.reply_text("',
            f'await update.message.reply_text("{WATERMARK_TEXT}\\n\\n',
            1,
        )

    try:
        target.write_text(new, encoding="utf-8")
        (root / "POWERED_BY_LUMEN.txt").write_text(WATERMARK_TEXT + "\n", encoding="utf-8")
        logger.info("watermark injected path=%s", target)
        return True
    except Exception as exc:
        logger.warning("watermark inject failed: %s", type(exc).__name__)
        return False
