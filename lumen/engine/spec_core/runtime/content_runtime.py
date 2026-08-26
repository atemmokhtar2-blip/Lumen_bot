"""Content + welcome runtime — durable rules/FAQ/welcome per chat."""
from __future__ import annotations

from app.db import connect, init_db


def ensure() -> None:
    init_db()
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS content_kv (
                chat_id INTEGER NOT NULL DEFAULT 0,
                kind TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                enabled INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, kind)
            );
            CREATE TABLE IF NOT EXISTS faq_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL DEFAULT 0,
                question TEXT NOT NULL,
                answer TEXT NOT NULL,
                hits INTEGER NOT NULL DEFAULT 0,
                active INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        conn.commit()


def rules(chat_id: int = 0) -> str:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT body FROM content_kv WHERE chat_id=? AND kind='rules'",
            (int(chat_id),),
        ).fetchone()
    if row and row["body"]:
        return row["body"]
    return (
        "【 القوانين 】\n"
        "1) احترم الأعضاء\n"
        "2) ممنوع السبام والروابط المشبوهة\n"
        "3) التزم بموضوع المجموعة\n"
        "المشرف يضبط القوانين بـ /setrules"
    )


def set_rules(chat_id: int, text: str) -> str:
    ensure()
    body = (text or "").strip()[:4000]
    if not body:
        return "❌ نص القوانين فارغ"
    with connect() as conn:
        conn.execute(
            "INSERT INTO content_kv (chat_id, kind, body, enabled) VALUES (?,?,?,1) "
            "ON CONFLICT(chat_id, kind) DO UPDATE SET body=excluded.body, updated_at=CURRENT_TIMESTAMP",
            (int(chat_id), "rules", body),
        )
        conn.commit()
    return "✅ تم حفظ القوانين"


def faq(user_id: int = 0, query: str = "") -> str:
    ensure()
    q = (query or "").strip()
    with connect() as conn:
        if q:
            like = f"%{q}%"
            rows = conn.execute(
                "SELECT id, question, answer FROM faq_items WHERE active=1 "
                "AND (question LIKE ? OR answer LIKE ?) ORDER BY hits DESC LIMIT 10",
                (like, like),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, question, answer FROM faq_items WHERE active=1 ORDER BY id DESC LIMIT 15"
            ).fetchall()
        if not rows:
            # seed defaults once
            n = conn.execute("SELECT COUNT(*) c FROM faq_items").fetchone()["c"]
            if int(n) == 0:
                seeds = [
                    ("كيف أبدأ؟", "أرسل /start ثم /help لعرض الأوامر."),
                    ("كيف أتواصل مع الدعم؟", "افتح تذكرة عبر /ticketopen أو راسل الإدارة."),
                    ("ما هي ساعات العمل؟", "الدعم متاح يومياً — أوقات الرد حسب الضغط."),
                ]
                for qq, aa in seeds:
                    conn.execute(
                        "INSERT INTO faq_items (chat_id, question, answer) VALUES (0,?,?)",
                        (qq, aa),
                    )
                conn.commit()
                rows = conn.execute(
                    "SELECT id, question, answer FROM faq_items WHERE active=1 LIMIT 15"
                ).fetchall()
    if not rows:
        return "لا أسئلة شائعة بعد"
    lines = ["【 الأسئلة الشائعة 】"]
    for r in rows:
        lines.append(f"• {r['question']}\n  → {r['answer']}")
    return "\n".join(lines)


def faq_add(admin_id: int, text: str) -> str:
    ensure()
    parts = [p.strip() for p in (text or "").split("|", 1)]
    if len(parts) < 2:
        return "الاستخدام: /faqadd سؤال | جواب"
    with connect() as conn:
        conn.execute(
            "INSERT INTO faq_items (chat_id, question, answer) VALUES (0,?,?)",
            (parts[0][:200], parts[1][:1000]),
        )
        conn.commit()
    return f"✅ أُضيف سؤال: {parts[0][:80]}"


def announce(text: str) -> str:
    body = (text or "").strip()
    if not body:
        return "❌ نص الإعلان فارغ"
    return f"📢 إعلان:\n{body[:2000]}"


def set_welcome(chat_id: int, text: str) -> str:
    ensure()
    body = (text or "").strip()[:2000]
    if not body:
        return "❌ رسالة الترحيب فارغة"
    with connect() as conn:
        conn.execute(
            "INSERT INTO content_kv (chat_id, kind, body, enabled) VALUES (?,?,?,1) "
            "ON CONFLICT(chat_id, kind) DO UPDATE SET body=excluded.body, enabled=1, "
            "updated_at=CURRENT_TIMESTAMP",
            (int(chat_id), "welcome", body),
        )
        conn.commit()
    return "✅ تم حفظ رسالة الترحيب"


def toggle_welcome(chat_id: int) -> bool:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT enabled, body FROM content_kv WHERE chat_id=? AND kind='welcome'",
            (int(chat_id),),
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO content_kv (chat_id, kind, body, enabled) VALUES (?,?,?,1)",
                (int(chat_id), "welcome", "أهلاً {name} في المجموعة!", 1),
            )
            conn.commit()
            return True
        new_v = 0 if int(row["enabled"]) else 1
        conn.execute(
            "UPDATE content_kv SET enabled=? WHERE chat_id=? AND kind='welcome'",
            (new_v, int(chat_id)),
        )
        conn.commit()
        return bool(new_v)


def get_settings(chat_id: int) -> dict:
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT body, enabled FROM content_kv WHERE chat_id=? AND kind='welcome'",
            (int(chat_id),),
        ).fetchone()
    if not row:
        return {"enabled": False, "message": ""}
    return {"enabled": bool(int(row["enabled"])), "message": row["body"] or ""}


def format_welcome(chat_id: int, name: str) -> str | None:
    cfg = get_settings(chat_id)
    if not cfg["enabled"]:
        return None
    msg = cfg["message"] or "أهلاً {name}!"
    return msg.replace("{name}", name or "عضو")
