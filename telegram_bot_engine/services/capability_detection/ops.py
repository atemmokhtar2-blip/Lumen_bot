"""Phase 13 — Ops commands (hardened): admin allowlist + confirm for mutations."""
from __future__ import annotations

import os
import time
from typing import Any

_LAST_MUTATION: dict[str, float] = {}
_MUTATION_COOLDOWN_SEC = 15.0


def _is_truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def ops_enabled() -> bool:
    return _is_truthy(os.getenv("CAPABILITY_OPS_COMMANDS", "1"))


def _parse_admin_ids() -> set[int]:
    raw = (
        os.getenv("CAPABILITY_OPS_ADMINS")
        or os.getenv("ADMIN_IDS")
        or os.getenv("ADMIN_USER_IDS")
        or ""
    )
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def is_ops_admin(user_id: int | None) -> bool:
    """If no admin list configured, allow (dev mode). If configured, enforce."""
    admins = _parse_admin_ids()
    if not admins:
        # Dev-friendly default; production should set CAPABILITY_OPS_ADMINS
        if _is_truthy(os.getenv("CAPABILITY_OPS_REQUIRE_ADMIN", "0")):
            return False
        return True
    if user_id is None:
        return False
    return int(user_id) in admins


def _cooldown_ok(key: str) -> bool:
    now = time.time()
    last = _LAST_MUTATION.get(key, 0.0)
    if now - last < _MUTATION_COOLDOWN_SEC:
        return False
    _LAST_MUTATION[key] = now
    return True


def handle_ops_command(text: str, *, user_id: int | None = None) -> str | None:
    """If text is an ops command, return Arabic response; else None."""
    if not ops_enabled():
        return None
    raw = (text or "").strip()
    if not raw.startswith("/"):
        return None
    parts = raw.split()
    cmd = parts[0].split("@", 1)[0].lower()
    arg = " ".join(parts[1:]).strip()
    args_l = arg.lower().split()

    if cmd not in {
        "/cap_help", "/capops", "/cap_health", "/cap_trace",
        "/cap_learn", "/cap_promote",
    }:
        return None

    if not is_ops_admin(user_id):
        return "⛔ أوامر القدرات متاحة للمشرفين فقط (CAPABILITY_OPS_ADMINS)."

    if cmd in {"/cap_help", "/capops"}:
        return (
            "🛠 أوامر القدرات (ops)\n"
            "/cap_health — صحة النظام\n"
            "/cap_trace <وصف> — تقرير المسار\n"
            "/cap_learn — إحصائيات التعلم\n"
            "/cap_learn run — دورة تعلم\n"
            "/cap_promote — حالة الترقية\n"
            "/cap_promote run confirm — ترقية المسودات (يتطلب تأكيد)\n"
            "الصلاحية: CAPABILITY_OPS_ADMINS أو ADMIN_IDS"
        )

    if cmd == "/cap_health":
        from .health import capability_system_health, health_summary_ar
        h = capability_system_health()
        lines = [health_summary_ar(h)]
        fails = [c for c in h.get("checks", []) if not c.get("ok")]
        if fails:
            lines.append("فشل:")
            for c in fails[:8]:
                lines.append(f"• {c.get('name')}: {c.get('detail')}")
        else:
            lines.append(f"فحوصات ناجحة: {h.get('passed')}")
        if h.get("log_path"):
            lines.append(f"log: {h.get('log_path')}")
        return "\n".join(lines)

    if cmd == "/cap_trace":
        from .pipeline_trace import pipeline_trace, fail_safe_message
        req = arg or "بوت ترحيب للمجموعة"
        tr = pipeline_trace(req, include_research=False)
        msg = fail_safe_message(tr)
        emit = tr.get("emit") or {}
        if emit.get("unsafe_count"):
            msg += f"\nemit unsafe: {emit.get('unsafe_count')}"
        return msg

    if cmd == "/cap_learn":
        from .learning_loop import learning_stats, run_learning_cycle
        if args_l and args_l[0] in {"run", "start", "go", "نفذ", "شغل"}:
            if not _cooldown_ok("learn"):
                return "⏳ انتظر قليلاً قبل إعادة تشغيل دورة التعلم."
            out = run_learning_cycle(min_count=1, limit=5, research=True)
            return (
                f"🧠 دورة تعلم: promoted={out.get('promoted')} skipped={out.get('skipped')}\n"
                f"KB={out.get('learned_kb_size')}"
            )
        st = learning_stats()
        top = st.get("top_gaps") or []
        lines = [
            "🧠 إحصائيات التعلم",
            f"entries={st.get('learned_entries')} drafts={st.get('draft_packs')} open_gaps={st.get('open_gaps')}",
        ]
        for g in top[:5]:
            lines.append(f"• {g.get('phrase')} ×{g.get('count')} ({g.get('status')})")
        lines.append("نفّذ: /cap_learn run")
        return "\n".join(lines)

    if cmd == "/cap_promote":
        from .pack_promotion import promotion_status, promote_latest_drafts
        if args_l and args_l[0] in {"run", "start", "go", "نفذ", "شغل"}:
            if "confirm" not in args_l and "تأكيد" not in args_l:
                return (
                    "⚠️ الترقية تغيّر السجل.\n"
                    "للتأكيد أرسل:\n"
                    "/cap_promote run confirm"
                )
            if not _cooldown_ok("promote"):
                return "⏳ انتظر قليلاً قبل ترقية أخرى."
            out = promote_latest_drafts(limit=3, require_safe_emit=True)
            return (
                f"📦 ترقية: installed={out.get('installed')} failed={out.get('failed')}\n"
                f"items={len(out.get('items') or [])}"
            )
        st = promotion_status()
        return (
            "📦 حالة الترقية\n"
            f"installed={st.get('installed_packs')} drafts={st.get('drafts')} learned={st.get('learned_entries')}\n"
            f"dir={st.get('install_dir')}\n"
            "للترقية: /cap_promote run confirm"
        )

    return None


__all__ = ["handle_ops_command", "ops_enabled", "is_ops_admin"]
