"""CRM / leads runtime — pipeline stages, not generic extras_kv.

Copied into generated bots as app/services/crm.py (or via extras lead_* APIs).
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.db import connect, init_db

_STAGES = ("new", "contacted", "qualified", "proposal", "won", "lost")
_STAGE_NEXT = {
    "new": frozenset({"contacted", "lost"}),
    "contacted": frozenset({"qualified", "lost"}),
    "qualified": frozenset({"proposal", "lost"}),
    "proposal": frozenset({"won", "lost"}),
    "won": frozenset(),
    "lost": frozenset({"new"}),
}


def ensure() -> None:
    init_db()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS crm_leads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL DEFAULT 0,
                name TEXT NOT NULL DEFAULT '',
                contact TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT 'telegram',
                stage TEXT NOT NULL DEFAULT 'new',
                value_cents INTEGER NOT NULL DEFAULT 0,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS crm_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                actor_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE INDEX IF NOT EXISTS idx_crm_owner ON crm_leads(owner_id, stage);
            """
        )
        conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def capture(owner_id: int, text: str) -> str:
    """Create lead from free text: name | contact | note."""
    ensure()
    parts = [p.strip() for p in (text or "").replace("،", "|").split("|")]
    name = parts[0] if parts else "عميل"
    contact = parts[1] if len(parts) > 1 else ""
    notes = parts[2] if len(parts) > 2 else (text or "")[:300]
    if not name:
        name = "عميل"
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO crm_leads (owner_id, name, contact, notes, stage, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (int(owner_id), name[:120], contact[:120], notes[:500], "new", _now()),
        )
        lid = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO crm_events (lead_id, event, note, actor_id) VALUES (?,?,?,?)",
            (lid, "captured", name, int(owner_id)),
        )
        conn.commit()
    return f"✅ عميل جديد #{lid}: {name}" + (f" ({contact})" if contact else "")


def list_leads(owner_id: int, stage: str | None = None, limit: int = 30) -> str:
    ensure()
    q = "SELECT id, name, contact, stage, value_cents, notes FROM crm_leads WHERE owner_id=?"
    params: list = [int(owner_id)]
    if stage:
        q += " AND stage=?"
        params.append(stage)
    q += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    with connect() as conn:
        rows = conn.execute(q, params).fetchall()
    if not rows:
        return "لا عملاء بعد — أضف: /lead اسم | هاتف | ملاحظة"
    return "\n".join(
        f"#{r['id']} [{r['stage']}] {r['name']}"
        + (f" — {r['contact']}" if r["contact"] else "")
        for r in rows
    )


def set_status(owner_id: int, text: str) -> str:
    """Usage: <lead_id> <stage>"""
    ensure()
    parts = (text or "").split()
    if len(parts) < 2:
        return "الاستخدام: /leadstatus <id> <stage>\nالمراحل: " + ", ".join(_STAGES)
    try:
        lid = int(parts[0])
    except ValueError:
        return "رقم عميل غير صالح"
    stage = parts[1].lower()
    if stage not in _STAGES:
        return "مراحل صالحة: " + ", ".join(_STAGES)
    with connect() as conn:
        row = conn.execute(
            "SELECT * FROM crm_leads WHERE id=? AND owner_id=?",
            (lid, int(owner_id)),
        ).fetchone()
        if not row:
            return f"❌ عميل #{lid} غير موجود"
        cur = (row["stage"] or "new").lower()
        allowed = _STAGE_NEXT.get(cur, frozenset())
        if stage not in allowed and stage != cur:
            return f"❌ انتقال غير مسموح: {cur} → {stage}"
        conn.execute(
            "UPDATE crm_leads SET stage=?, updated_at=? WHERE id=?",
            (stage, _now(), lid),
        )
        conn.execute(
            "INSERT INTO crm_events (lead_id, event, note, actor_id) VALUES (?,?,?,?)",
            (lid, f"stage:{stage}", cur, int(owner_id)),
        )
        conn.commit()
    return f"✅ عميل #{lid}: {cur} → {stage}"


def set_followup(owner_id: int, text: str) -> str:
    """Attach follow-up note: <lead_id> <note>"""
    ensure()
    parts = (text or "").strip().split(None, 1)
    if len(parts) < 2:
        return "الاستخدام: /followup <id> ملاحظة المتابعة"
    try:
        lid = int(parts[0])
    except ValueError:
        return "رقم غير صالح"
    note = parts[1][:500]
    with connect() as conn:
        row = conn.execute(
            "SELECT id FROM crm_leads WHERE id=? AND owner_id=?",
            (lid, int(owner_id)),
        ).fetchone()
        if not row:
            return f"❌ عميل #{lid} غير موجود"
        conn.execute(
            "UPDATE crm_leads SET notes=notes || ? || ?, updated_at=? WHERE id=?",
            ("\n• ", note, _now(), lid),
        )
        conn.execute(
            "INSERT INTO crm_events (lead_id, event, note, actor_id) VALUES (?,?,?,?)",
            (lid, "followup", note[:120], int(owner_id)),
        )
        conn.commit()
    return f"✅ متابعة على عميل #{lid}"


def pipeline_summary(owner_id: int) -> str:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT stage, COUNT(*) c FROM crm_leads WHERE owner_id=? GROUP BY stage",
            (int(owner_id),),
        ).fetchall()
    if not rows:
        return "خط الأنابيب فارغ"
    counts = {r["stage"]: int(r["c"]) for r in rows}
    lines = ["【 خط أنابيب المبيعات 】"]
    for s in _STAGES:
        lines.append(f"• {s}: {counts.get(s, 0)}")
    return "\n".join(lines)


# Handler-friendly aliases matching registry methods
def lead_capture(user_id: int, text: str = "") -> str:
    return capture(user_id, text)


def lead_list(user_id: int, text: str = "") -> str:
    return list_leads(user_id)


def lead_status(user_id: int, text: str = "") -> str:
    return set_status(user_id, text)


def followup_set(user_id: int, text: str = "") -> str:
    return set_followup(user_id, text)


def act(entity: str, method: str, user_id: int, text: str = "") -> str:
    m = (method or "").lower()
    if m in {"lead_capture", "capture", "add", "create"}:
        return capture(user_id, text)
    if m in {"lead_list", "list", "my"}:
        return list_leads(user_id)
    if m in {"lead_status", "status", "set_status"}:
        return set_status(user_id, text)
    if m in {"followup_set", "followup"}:
        return set_followup(user_id, text)
    if m in {"pipeline", "summary"}:
        return pipeline_summary(user_id)
    return f"{method} is not available in this bot build"
