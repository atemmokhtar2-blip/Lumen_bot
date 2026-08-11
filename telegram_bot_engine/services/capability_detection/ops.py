"""Phase 13 — Ops commands for capability pipeline (admin-facing text)."""
from __future__ import annotations

import os
from typing import Any


def _is_truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in {"1", "true", "yes", "on"}


def ops_enabled() -> bool:
    return _is_truthy(os.getenv("CAPABILITY_OPS_COMMANDS", "1"))


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

    if cmd in {"/cap_help", "/capops"}:
        return (
            "🛠 أوامر القدرات (ops)\n"
            "/cap_health — صحة النظام\n"
            "/cap_trace <وصف> — تقرير المسار\n"
            "/cap_learn — إحصائيات التعلم (أو /cap_learn run)\n"
            "/cap_promote — حالة الترقية (أو /cap_promote run)\n"
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
        return "\n".join(lines)

    if cmd == "/cap_trace":
        from .pipeline_trace import pipeline_trace, fail_safe_message
        req = arg or "بوت ترحيب للمجموعة"
        tr = pipeline_trace(req, include_research=False)
        return fail_safe_message(tr)

    if cmd == "/cap_learn":
        from .learning_loop import learning_stats, run_learning_cycle
        if arg.lower() in {"run", "start", "go", "نفذ", "شغل"}:
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
        if arg.lower() in {"run", "start", "go", "نفذ", "شغل"}:
            out = promote_latest_drafts(limit=3, require_safe_emit=True)
            return f"📦 ترقية: installed={out.get('installed')} failed={out.get('failed')}"
        st = promotion_status()
        return (
            "📦 حالة الترقية\n"
            f"installed={st.get('installed_packs')} drafts={st.get('drafts')} learned={st.get('learned_entries')}\n"
            f"dir={st.get('install_dir')}\n"
            "نفّذ: /cap_promote run"
        )

    return None
