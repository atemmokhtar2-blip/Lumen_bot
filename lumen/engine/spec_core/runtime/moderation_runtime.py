"""Moderation service — ranks, warns, protection, anti-raid, per-chat settings."""
from __future__ import annotations

import re
import time
from collections import defaultdict
from telegram import ChatPermissions
from telegram.ext import ContextTypes

from app.db import connect, init_db

_flood_bucket: dict[tuple[int, int], list[float]] = defaultdict(list)
_join_bucket: dict[int, list[float]] = defaultdict(list)

ROLE_ORDER = {"member": 0, "moderator": 1, "admin": 2, "owner": 3}


def ensure() -> None:
    init_db()
    with connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS warns ("
            "chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
            "count INTEGER NOT NULL DEFAULT 0, last_ts INTEGER NOT NULL DEFAULT 0, "
            "PRIMARY KEY (chat_id, user_id))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS admin_log ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id INTEGER NOT NULL, "
            "admin_id INTEGER NOT NULL, action TEXT NOT NULL, target_id INTEGER NOT NULL DEFAULT 0, "
            "detail TEXT NOT NULL DEFAULT '', ts INTEGER NOT NULL)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS chat_settings ("
            "chat_id INTEGER PRIMARY KEY, "
            "max_warns INTEGER NOT NULL DEFAULT 3, "
            "warn_ttl_hours INTEGER NOT NULL DEFAULT 168, "
            "anti_link INTEGER NOT NULL DEFAULT 1, "
            "anti_spam INTEGER NOT NULL DEFAULT 1, "
            "anti_flood INTEGER NOT NULL DEFAULT 1, "
            "anti_raid INTEGER NOT NULL DEFAULT 1, "
            "flood_limit INTEGER NOT NULL DEFAULT 6, "
            "flood_window INTEGER NOT NULL DEFAULT 8, "
            "raid_joins INTEGER NOT NULL DEFAULT 8, "
            "raid_window INTEGER NOT NULL DEFAULT 20, "
            "escalation TEXT NOT NULL DEFAULT 'warn,mute,kick,ban', "
            "owner_id INTEGER NOT NULL DEFAULT 0, "
            "leave_msg TEXT NOT NULL DEFAULT '', "
            "leave_on INTEGER NOT NULL DEFAULT 0, "
            "rules_on_join INTEGER NOT NULL DEFAULT 1)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS chat_roles ("
            "chat_id INTEGER NOT NULL, user_id INTEGER NOT NULL, "
            "role TEXT NOT NULL DEFAULT 'member', "
            "PRIMARY KEY (chat_id, user_id))"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS forbidden_words ("
            "chat_id INTEGER NOT NULL, word TEXT NOT NULL, "
            "PRIMARY KEY (chat_id, word))"
        )
        conn.commit()


def log_action(chat_id: int, admin_id: int, action: str, target_id: int = 0, detail: str = "") -> None:
    ensure()
    with connect() as conn:
        conn.execute(
            "INSERT INTO admin_log (chat_id, admin_id, action, target_id, detail, ts) VALUES (?, ?, ?, ?, ?, ?)",
            (int(chat_id), int(admin_id), action, int(target_id), (detail or "")[:300], int(time.time())),
        )
        conn.commit()


def list_log(chat_id: int, limit: int = 15) -> str:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT action, admin_id, target_id, detail, ts FROM admin_log "
            "WHERE chat_id = ? ORDER BY id DESC LIMIT ?",
            (int(chat_id), max(1, min(limit, 40))),
        ).fetchall()
    if not rows:
        return "لا أحداث في السجل"
    out = []
    for r in rows:
        ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(int(r["ts"])))
        out.append(f"• [{ts}] {r['action']} by={r['admin_id']} target={r['target_id']} {r['detail']}")
    return "\n".join(out)


def get_settings(chat_id: int) -> dict:
    ensure()
    with connect() as conn:
        row = conn.execute("SELECT * FROM chat_settings WHERE chat_id = ?", (int(chat_id),)).fetchone()
    if not row:
        return {
            "max_warns": 3, "warn_ttl_hours": 168,
            "anti_link": 1, "anti_spam": 1, "anti_flood": 1, "anti_raid": 1,
            "flood_limit": 6, "flood_window": 8, "raid_joins": 8, "raid_window": 20,
            "escalation": "warn,mute,kick,ban", "owner_id": 0,
            "leave_msg": "", "leave_on": 0, "rules_on_join": 1,
        }
    return dict(row)


def _upsert_settings(chat_id: int, **fields) -> None:
    ensure()
    cur = get_settings(chat_id)
    cur.update({k: v for k, v in fields.items() if v is not None})
    vals = (
        int(chat_id),
        int(cur["max_warns"]), int(cur["warn_ttl_hours"]),
        int(cur["anti_link"]), int(cur["anti_spam"]), int(cur["anti_flood"]), int(cur["anti_raid"]),
        int(cur["flood_limit"]), int(cur["flood_window"]), int(cur["raid_joins"]), int(cur["raid_window"]),
        str(cur.get("escalation") or "warn,mute,kick,ban"),
        int(cur.get("owner_id") or 0),
        str(cur.get("leave_msg") or "")[:500],
        int(cur.get("leave_on") or 0),
        int(cur.get("rules_on_join") if cur.get("rules_on_join") is not None else 1),
    )
    with connect() as conn:
        conn.execute(
            "INSERT INTO chat_settings ("
            "chat_id, max_warns, warn_ttl_hours, anti_link, anti_spam, anti_flood, anti_raid, "
            "flood_limit, flood_window, raid_joins, raid_window, escalation, owner_id, "
            "leave_msg, leave_on, rules_on_join) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
            "ON CONFLICT(chat_id) DO UPDATE SET "
            "max_warns=excluded.max_warns, warn_ttl_hours=excluded.warn_ttl_hours, "
            "anti_link=excluded.anti_link, anti_spam=excluded.anti_spam, "
            "anti_flood=excluded.anti_flood, anti_raid=excluded.anti_raid, "
            "flood_limit=excluded.flood_limit, flood_window=excluded.flood_window, "
            "raid_joins=excluded.raid_joins, raid_window=excluded.raid_window, "
            "escalation=excluded.escalation, owner_id=excluded.owner_id, "
            "leave_msg=excluded.leave_msg, leave_on=excluded.leave_on, "
            "rules_on_join=excluded.rules_on_join",
            vals,
        )
        conn.commit()


def set_max_warns(chat_id: int, n: int) -> str:
    n = max(1, min(int(n), 20))
    _upsert_settings(chat_id, max_warns=n)
    return f"حد التحذيرات أصبح {n}"


def set_protection(
    chat_id: int,
    anti_link: int | None = None,
    anti_spam: int | None = None,
    anti_flood: int | None = None,
    anti_raid: int | None = None,
) -> str:
    fields = {}
    if anti_link is not None:
        fields["anti_link"] = 1 if anti_link else 0
    if anti_spam is not None:
        fields["anti_spam"] = 1 if anti_spam else 0
    if anti_flood is not None:
        fields["anti_flood"] = 1 if anti_flood else 0
    if anti_raid is not None:
        fields["anti_raid"] = 1 if anti_raid else 0
    if fields:
        _upsert_settings(chat_id, **fields)
    s = get_settings(chat_id)
    return (
        f"الحماية: روابط={'تشغيل' if s['anti_link'] else 'إيقاف'} | "
        f"سبام={'تشغيل' if s['anti_spam'] else 'إيقاف'} | "
        f"فيض={'تشغيل' if s['anti_flood'] else 'إيقاف'} | "
        f"غارة={'تشغيل' if s['anti_raid'] else 'إيقاف'}"
    )


def set_owner(chat_id: int, user_id: int) -> str:
    _upsert_settings(chat_id, owner_id=int(user_id))
    set_role(chat_id, int(user_id), "owner")
    return f"تم تعيين Owner: {user_id}"


def get_role(chat_id: int, user_id: int) -> str:
    ensure()
    s = get_settings(chat_id)
    if int(s.get("owner_id") or 0) == int(user_id):
        return "owner"
    with connect() as conn:
        row = conn.execute(
            "SELECT role FROM chat_roles WHERE chat_id = ? AND user_id = ?",
            (int(chat_id), int(user_id)),
        ).fetchone()
    return str(row["role"]) if row else "member"


def set_role(chat_id: int, user_id: int, role: str) -> str:
    role = (role or "member").lower().strip()
    if role not in ROLE_ORDER:
        role = "member"
    ensure()
    with connect() as conn:
        conn.execute(
            "INSERT INTO chat_roles (chat_id, user_id, role) VALUES (?, ?, ?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET role = excluded.role",
            (int(chat_id), int(user_id), role),
        )
        conn.commit()
    return f"رتبة {user_id}: {role}"


def can_act(chat_id: int, actor_id: int, target_id: int, min_role: str = "moderator") -> tuple[bool, str]:
    actor_role = get_role(chat_id, actor_id)
    target_role = get_role(chat_id, target_id)
    if target_role == "owner" and actor_role != "owner":
        return False, "لا يمكن المساس بالـ Owner"
    if ROLE_ORDER.get(actor_role, 0) < ROLE_ORDER.get(min_role, 1):
        return False, f"صلاحيتك ({actor_role}) أقل من المطلوب ({min_role})"
    if int(actor_id) != int(target_id) and ROLE_ORDER.get(actor_role, 0) <= ROLE_ORDER.get(target_role, 0):
        if actor_role != "owner":
            return False, "لا يمكنك تنفيذ إجراء على رتبة مساوية أو أعلى"
    return True, "ok"


def is_owner_protected(chat_id: int, user_id: int) -> bool:
    return get_role(chat_id, user_id) == "owner"


def list_forbidden(chat_id: int) -> list[str]:
    ensure()
    with connect() as conn:
        rows = conn.execute(
            "SELECT word FROM forbidden_words WHERE chat_id = ? ORDER BY word",
            (int(chat_id),),
        ).fetchall()
    return [str(r["word"]) for r in rows]


def add_forbidden(chat_id: int, word: str) -> str:
    w = (word or "").strip().lower()
    if not w or len(w) > 64:
        return "كلمة غير صالحة"
    ensure()
    with connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO forbidden_words (chat_id, word) VALUES (?, ?)",
            (int(chat_id), w),
        )
        conn.commit()
    return f"أُضيفت للكلمات الممنوعة: {w}"


def remove_forbidden(chat_id: int, word: str) -> str:
    w = (word or "").strip().lower()
    ensure()
    with connect() as conn:
        conn.execute(
            "DELETE FROM forbidden_words WHERE chat_id = ? AND word = ?",
            (int(chat_id), w),
        )
        conn.commit()
    return f"حُذفت من الممنوعة: {w}"


def has_forbidden(chat_id: int, text: str) -> str | None:
    words = list_forbidden(chat_id)
    if not words:
        return None
    t = (text or "").lower()
    for w in words:
        if w and w in t:
            return w
    return None


def _purge_expired_warns(chat_id: int, user_id: int) -> None:
    s = get_settings(chat_id)
    ttl = max(1, int(s.get("warn_ttl_hours") or 168)) * 3600
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT count, last_ts FROM warns WHERE chat_id = ? AND user_id = ?",
            (int(chat_id), int(user_id)),
        ).fetchone()
        if not row:
            return
        if int(row["last_ts"] or 0) and (time.time() - int(row["last_ts"])) > ttl:
            conn.execute(
                "UPDATE warns SET count = 0, last_ts = 0 WHERE chat_id = ? AND user_id = ?",
                (int(chat_id), int(user_id)),
            )
            conn.commit()


def get_warns(chat_id: int, user_id: int) -> int:
    _purge_expired_warns(chat_id, user_id)
    ensure()
    with connect() as conn:
        row = conn.execute(
            "SELECT count FROM warns WHERE chat_id = ? AND user_id = ?",
            (int(chat_id), int(user_id)),
        ).fetchone()
    return int(row["count"]) if row else 0


def clear_warnings(chat_id: int, user_id: int) -> str:
    ensure()
    with connect() as conn:
        conn.execute(
            "DELETE FROM warns WHERE chat_id = ? AND user_id = ?",
            (int(chat_id), int(user_id)),
        )
        conn.commit()
    return f"تم مسح تحذيرات {user_id}"


def unwarn_user(chat_id: int, user_id: int) -> str:
    ensure()
    n = get_warns(chat_id, user_id)
    if n <= 0:
        return "لا توجد تحذيرات"
    with connect() as conn:
        conn.execute(
            "UPDATE warns SET count = ? WHERE chat_id = ? AND user_id = ?",
            (n - 1, int(chat_id), int(user_id)),
        )
        conn.commit()
    return f"تحذيرات {user_id}: {n - 1}"


async def _apply_escalation(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, count: int) -> str:
    s = get_settings(chat_id)
    max_w = max(1, int(s.get("max_warns") or 3))
    steps = [x.strip() for x in str(s.get("escalation") or "warn,mute,kick,ban").split(",") if x.strip()]
    if count < max_w:
        return f"تحذير {count}/{max_w}"
    action = steps[min(len(steps) - 1, max(0, count - max_w))] if steps else "mute"
    if action == "mute":
        await mute_user(context, chat_id, user_id)
        return f"تصعيد: كتم (تحذيرات={count})"
    if action == "kick":
        await kick_user(context, chat_id, user_id)
        return f"تصعيد: طرد (تحذيرات={count})"
    if action == "ban":
        await ban_user(context, chat_id, user_id)
        return f"تصعيد: حظر (تحذيرات={count})"
    return f"تحذير {count}/{max_w}"


async def warn_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, admin_id: int = 0) -> str:
    if is_owner_protected(chat_id, user_id):
        return "لا يمكن تحذير الـ Owner"
    if admin_id:
        ok, reason = can_act(chat_id, admin_id, user_id, "moderator")
        if not ok:
            return reason
    ensure()
    _purge_expired_warns(chat_id, user_id)
    with connect() as conn:
        row = conn.execute(
            "SELECT count FROM warns WHERE chat_id = ? AND user_id = ?",
            (int(chat_id), int(user_id)),
        ).fetchone()
        n = (int(row["count"]) if row else 0) + 1
        conn.execute(
            "INSERT INTO warns (chat_id, user_id, count, last_ts) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(chat_id, user_id) DO UPDATE SET count = excluded.count, last_ts = excluded.last_ts",
            (int(chat_id), int(user_id), n, int(time.time())),
        )
        conn.commit()
    if admin_id:
        log_action(chat_id, admin_id, "warn", user_id, f"count={n}")
    return await _apply_escalation(context, chat_id, user_id, n)


async def ban_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    if is_owner_protected(chat_id, user_id):
        return
    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)


async def unban_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)


async def mute_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int, seconds: int = 3600) -> None:
    if is_owner_protected(chat_id, user_id):
        return
    until = int(time.time()) + max(30, int(seconds))
    perms = ChatPermissions(can_send_messages=False)
    await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=perms, until_date=until)


async def unmute_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    perms = ChatPermissions(
        can_send_messages=True, can_send_media_messages=True,
        can_send_other_messages=True, can_add_web_page_previews=True,
    )
    await context.bot.restrict_chat_member(chat_id=chat_id, user_id=user_id, permissions=perms)


async def kick_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    if is_owner_protected(chat_id, user_id):
        return
    await context.bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
    await context.bot.unban_chat_member(chat_id=chat_id, user_id=user_id)


async def promote_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    await context.bot.promote_chat_member(
        chat_id=chat_id, user_id=user_id,
        can_delete_messages=True, can_restrict_members=True,
        can_invite_users=True, can_pin_messages=True, can_promote_members=False,
    )
    set_role(chat_id, user_id, "admin")


async def demote_user(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user_id: int) -> None:
    if is_owner_protected(chat_id, user_id):
        return
    await context.bot.promote_chat_member(
        chat_id=chat_id, user_id=user_id,
        can_delete_messages=False, can_restrict_members=False,
        can_invite_users=False, can_pin_messages=False, can_promote_members=False,
    )
    set_role(chat_id, user_id, "member")


async def pin_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    await context.bot.pin_chat_message(chat_id=chat_id, message_id=message_id)


async def delete_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)


async def purge(context: ContextTypes.DEFAULT_TYPE, chat_id: int, message_id: int) -> None:
    await context.bot.delete_message(chat_id=chat_id, message_id=message_id)


def slowmode_info() -> str:
    return "الوضع البطيء يُضبط من إعدادات تيليجرام للجروب أو عبر صلاحيات البوت إن توفرت."


def user_info(user_id: int, chat_id: int = 0) -> str:
    role = get_role(chat_id, user_id) if chat_id else "member"
    warns = get_warns(chat_id, user_id) if chat_id else 0
    return f"المعرف: {user_id}\nالرتبة: {role}\nالتحذيرات: {warns}"


def looks_like_link(text: str) -> bool:
    t = (text or "").lower()
    return ("http://" in t) or ("https://" in t) or ("t.me/" in t) or ("www." in t)


def looks_like_spam(text: str) -> bool:
    t = (text or "").strip()
    if len(t) > 800:
        return True
    if t and len(set(t)) <= 2 and len(t) >= 12:
        return True
    if len(re.findall(r"(.)\1{6,}", t)) >= 1:
        return True
    return False


def record_message_flood(chat_id: int, user_id: int) -> bool:
    s = get_settings(chat_id)
    if not int(s.get("anti_flood") or 0):
        return False
    now = time.time()
    window = max(3, int(s.get("flood_window") or 8))
    limit = max(3, int(s.get("flood_limit") or 6))
    key = (int(chat_id), int(user_id))
    bucket = [t for t in _flood_bucket[key] if now - t <= window]
    bucket.append(now)
    _flood_bucket[key] = bucket
    return len(bucket) > limit


def record_join(chat_id: int) -> bool:
    s = get_settings(chat_id)
    if not int(s.get("anti_raid") or 0):
        return False
    now = time.time()
    window = max(5, int(s.get("raid_window") or 20))
    limit = max(3, int(s.get("raid_joins") or 8))
    bucket = [t for t in _join_bucket[int(chat_id)] if now - t <= window]
    bucket.append(now)
    _join_bucket[int(chat_id)] = bucket
    return len(bucket) > limit


def set_leave_message(chat_id: int, text: str, enabled: int = 1) -> str:
    _upsert_settings(chat_id, leave_msg=(text or "")[:500], leave_on=1 if enabled else 0)
    return "تم تحديث رسالة المغادرة"


def get_leave_message(chat_id: int) -> str:
    s = get_settings(chat_id)
    if not int(s.get("leave_on") or 0):
        return ""
    return str(s.get("leave_msg") or "")
