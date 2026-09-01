"""Send engine presentation tables to Telegram (Rich Messages)."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def send_engine_presentation(
    *,
    bot: Any,
    chat_id: int | None,
    metadata: dict[str, Any] | None,
    stages: list | None = None,
    user_data: dict | None = None,
) -> bool:
    """Return True if a rich table was sent."""
    if bot is None or chat_id is None:
        return False
    meta = metadata if isinstance(metadata, dict) else {}
    try:
        from lumen.engine.services.presentation.table_policy import (
            table_from_explicit,
            table_from_stages,
            TableSpec,
        )
        from lumen.bot.rich_messages import send_table_spec

        spec = None
        pres = meta.get("presentation")
        if isinstance(pres, dict):
            spec = table_from_explicit(pres)
        if spec is None:
            st = stages if stages is not None else meta.get("stages")
            if isinstance(st, list) and st:
                stage_dicts = []
                for s in st:
                    if isinstance(s, dict):
                        stage_dicts.append(s)
                    else:
                        stage_dicts.append({
                            "name": getattr(s, "name", None) or "stage",
                            "success": getattr(s, "success", None),
                            "detail": getattr(s, "detail", None) or "",
                        })
                spec = table_from_stages(stage_dicts)
        # Synthesize minimal engine path if still empty but we have status flags
        if spec is None and (meta.get("status") or meta.get("qa_passed") is not None):
            rows = [
                ["1", "الحالة", str(meta.get("status") or "—")[:28], ""],
                ["2", "QA", "نجاح" if meta.get("qa_passed") else "—", ""],
                ["3", "البناء", "نجاح" if meta.get("build_success") else "—", ""],
            ]
            if meta.get("attempts"):
                rows.append(["4", "المحاولات", str(meta.get("attempts")), ""])
            if len(rows) >= 2:
                spec = TableSpec(
                    headers=["#", "البند", "القيمة", "ملاحظة"],
                    rows=rows,
                    caption="ملخص المحرك",
                    kind="metrics",
                    reason="metadata synthesis",
                    title="مسار المحرك",
                )
        if spec is None:
            return False
        result = await send_table_spec(
            bot, chat_id=int(chat_id), spec=spec, user_data=user_data
        )
        return result is not None
    except Exception:
        logger.exception("send_engine_presentation failed")
        return False
