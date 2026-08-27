"""Set PostgreSQL app.tenant_id for RLS on each connection."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def set_tenant_context(conn: Any, tenant_id: str) -> None:
    """SET LOCAL app.tenant_id so RLS policies apply for this transaction."""
    tid = str(tenant_id or "").strip()
    if not tid:
        return
    try:
        # psycopg3
        conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tid,))
    except Exception:
        try:
            cur = conn.cursor()
            cur.execute("SELECT set_config(%s, %s, true)", ("app.tenant_id", tid))
        except Exception:
            logger.debug("set_tenant_context failed", exc_info=True)
