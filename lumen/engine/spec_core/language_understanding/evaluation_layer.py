"""Stage-5 Evaluation & Optimization Layer.

- Feedback collection (ties to Stage-3)
- A/B testing of narrative / response variants
- Performance analytics (success rate, corrections, ratings, learning velocity)

All on SQLite via MemoryEngine events — no external analytics SaaS.
"""
from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass, field
from typing import Any

from .memory_engine import MemoryEngine, get_memory_engine


# ── A/B variants for Stage-4 narratives ─────────────────────────────────────
AB_VARIANTS: dict[str, dict[str, Any]] = {
    "A": {
        "id": "A",
        "label": "detailed",
        "show_menu": True,
        "show_domain": True,
        "show_learning_notes": True,
        "status_verbose": True,
        "max_questions": 3,
        "suggestion_extra": 2,
        "pre_summary_rich": True,
    },
    "B": {
        "id": "B",
        "label": "compact",
        "show_menu": True,
        "show_domain": False,
        "show_learning_notes": False,
        "status_verbose": False,
        "max_questions": 1,
        "suggestion_extra": 0,
        "pre_summary_rich": False,
    },
}


@dataclass
class ABAssignment:
    user_id: int
    variant: str  # A | B
    reason: str = "hash"

    def to_dict(self) -> dict[str, Any]:
        return {"user_id": self.user_id, "variant": self.variant, "reason": self.reason}


@dataclass
class PerformanceReport:
    window_hours: float
    generations: int = 0
    successes: int = 0
    failures: int = 0
    success_rate: float = 0.0
    feedback_count: int = 0
    avg_rating: float | None = None
    positive_feedback: int = 0
    negative_feedback: int = 0
    corrections: int = 0
    strict_builds: int = 0
    ab_stats: dict[str, dict[str, Any]] = field(default_factory=dict)
    top_intents: list[tuple[str, int]] = field(default_factory=list)
    learning_velocity: float = 0.0  # net score delta / generations
    notes: list[str] = field(default_factory=list)
    feature_leaderboard: list[dict[str, Any]] = field(default_factory=list)
    ab_winner: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "window_hours": self.window_hours,
            "generations": self.generations,
            "successes": self.successes,
            "failures": self.failures,
            "success_rate": round(self.success_rate, 3),
            "feedback_count": self.feedback_count,
            "avg_rating": round(self.avg_rating, 2) if self.avg_rating is not None else None,
            "positive_feedback": self.positive_feedback,
            "negative_feedback": self.negative_feedback,
            "corrections": self.corrections,
            "strict_builds": self.strict_builds,
            "ab_stats": self.ab_stats,
            "top_intents": self.top_intents[:8],
            "learning_velocity": round(self.learning_velocity, 3),
            "notes": self.notes[:6],
            "feature_leaderboard": self.feature_leaderboard[:10],
            "ab_winner": self.ab_winner,
        }

    def to_arabic(self) -> str:
        lines = [
            "📊 تقرير الأداء (مرحلة 5)",
            f"• النافذة: آخر {self.window_hours:g} ساعة",
            f"• توليدات: {self.generations} | نجاح: {self.successes} | فشل: {self.failures}",
            f"• معدل النجاح: {self.success_rate * 100:.0f}%",
            f"• تقييمات: {self.feedback_count}"
            + (f" | متوسط {self.avg_rating:.1f}/5" if self.avg_rating is not None else ""),
            f"• إيجابي: {self.positive_feedback} · سلبي: {self.negative_feedback}",
            f"• تصحيحات: {self.corrections} · strict: {self.strict_builds}",
            f"• سرعة التعلم (صافي): {self.learning_velocity:+.2f}",
        ]
        if self.ab_stats:
            lines.append("• A/B:")
            for vid, st in self.ab_stats.items():
                lines.append(
                    f"  – {vid}: n={st.get('n', 0)} success={st.get('success_rate', 0)*100:.0f}% "
                    f"rating={st.get('avg_rating', '—')}"
                )
        if self.top_intents:
            tops = ", ".join(f"{k}({v})" for k, v in self.top_intents[:5])
            lines.append(f"• أشهر intents: {tops}")
        if self.ab_winner:
            lines.append(f"• 🏆 فائز A/B الحالي: {self.ab_winner}")
        if self.feature_leaderboard:
            lines.append("• ميزات الأعلى نجاحًا:")
            for item in self.feature_leaderboard[:5]:
                lines.append(
                    f"  – {item.get('feature')}: "
                    f"{float(item.get('success_rate') or 0)*100:.0f}% "
                    f"(n={item.get('n', 0)})"
                )
        for n in self.notes[:3]:
            lines.append(f"• 💡 {n}")
        return "\n".join(lines)


def assign_ab_variant(user_id: int) -> ABAssignment:
    """Stable per-user A/B assignment (50/50 by hash)."""
    if not user_id:
        return ABAssignment(0, "A", reason="anon")
    h = hashlib.md5(f"ab:{int(user_id)}".encode()).hexdigest()
    variant = "A" if int(h[:8], 16) % 2 == 0 else "B"
    return ABAssignment(int(user_id), variant, reason="md5")


def get_ab_config(user_id: int) -> dict[str, Any]:
    asg = assign_ab_variant(user_id)
    cfg = dict(AB_VARIANTS.get(asg.variant) or AB_VARIANTS["A"])
    cfg["assignment"] = asg.to_dict()
    return cfg


def apply_ab_to_narrative(narrative_dict: dict[str, Any], user_id: int) -> dict[str, Any]:
    """Filter narrative fields according to A/B variant."""
    cfg = get_ab_config(user_id)
    out = dict(narrative_dict or {})
    out["ab_variant"] = cfg.get("id")
    if not cfg.get("show_menu"):
        out["menu_preview"] = []
    if not cfg.get("show_domain") and out.get("pre_summary"):
        # strip domain line if present
        lines = str(out["pre_summary"]).split("\n")
        lines = [ln for ln in lines if not ln.startswith("المجال:") and not ln.startswith("Domain:")]
        out["pre_summary"] = "\n".join(lines)
    if not cfg.get("show_learning_notes"):
        out["adaptation_notes"] = []
    if not cfg.get("status_verbose"):
        # compact status
        name = ""
        body = str(out.get("status_start") or "")
        if "«" in body and "»" in body:
            name = body[body.find("«") : body.find("»") + 1]
        out["status_start"] = f"⏳ {name or 'توليد'}…".strip()
    return out


def record_generation_outcome(
    user_id: int,
    *,
    success: bool,
    intent: str | None = None,
    strict: bool = False,
    feature_count: int = 0,
    preset: str | None = None,
    ab_variant: str | None = None,
    elapsed_ms: float | None = None,
    memory: MemoryEngine | None = None,
) -> None:
    mem = memory or get_memory_engine()
    if not user_id:
        return
    if ab_variant is None:
        ab_variant = assign_ab_variant(int(user_id)).variant
    try:
        mem._event(
            int(user_id),
            "gen_outcome",
            {
                "success": bool(success),
                "intent": intent or "",
                "strict": bool(strict),
                "feature_count": int(feature_count),
                "preset": preset or "",
                "ab": ab_variant,
                "elapsed_ms": elapsed_ms,
                "ts": time.time(),
            },
        )
    except Exception:
        pass


def record_ab_exposure(
    user_id: int,
    variant: str,
    *,
    surface: str = "narrative",
    memory: MemoryEngine | None = None,
) -> None:
    mem = memory or get_memory_engine()
    if not user_id:
        return
    try:
        mem._event(
            int(user_id),
            "ab_exposure",
            {"variant": variant, "surface": surface, "ts": time.time()},
        )
    except Exception:
        pass


def build_performance_report(
    *,
    window_hours: float = 24.0,
    memory: MemoryEngine | None = None,
    user_id: int | None = None,
) -> PerformanceReport:
    """Aggregate Stage-5 metrics from event_log + feedback + bots_built."""
    mem = memory or get_memory_engine()
    cutoff = time.time() - float(window_hours) * 3600.0
    report = PerformanceReport(window_hours=window_hours)

    gen_rows: list[dict] = []
    try:
        with mem._conn() as conn:
            q = "SELECT user_id, payload_json, created_at FROM event_log WHERE event=? AND created_at>=?"
            args: list[Any] = ["gen_outcome", cutoff]
            if user_id:
                q += " AND user_id=?"
                args.append(int(user_id))
            rows = conn.execute(q + " ORDER BY id DESC LIMIT 2000", tuple(args)).fetchall()
            for r in rows:
                try:
                    data = json.loads(r["payload_json"] or "{}")
                except Exception:
                    data = {}
                data["_uid"] = r["user_id"]
                gen_rows.append(data)
    except Exception:
        gen_rows = []

    report.generations = len(gen_rows)
    report.successes = sum(1 for g in gen_rows if g.get("success"))
    report.failures = report.generations - report.successes
    report.success_rate = (report.successes / report.generations) if report.generations else 0.0
    report.strict_builds = sum(1 for g in gen_rows if g.get("strict"))

    intent_counts: dict[str, int] = {}
    ab_bucket: dict[str, dict[str, Any]] = {}
    for g in gen_rows:
        intent = str(g.get("intent") or "unknown")
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
        ab = str(g.get("ab") or "?")
        b = ab_bucket.setdefault(ab, {"n": 0, "ok": 0, "ratings": []})
        b["n"] += 1
        if g.get("success"):
            b["ok"] += 1

    report.top_intents = sorted(intent_counts.items(), key=lambda x: -x[1])[:8]

    # feedback
    ratings: list[int] = []
    try:
        with mem._conn() as conn:
            q = "SELECT user_id, rating, liked, disliked, created_at FROM user_feedback WHERE created_at>=?"
            args2: list[Any] = [cutoff]
            if user_id:
                q += " AND user_id=?"
                args2.append(int(user_id))
            frows = conn.execute(q + " ORDER BY id DESC LIMIT 1000", tuple(args2)).fetchall()
            for r in frows:
                report.feedback_count += 1
                rating = int(r["rating"] or 0)
                if rating:
                    ratings.append(rating)
                if rating >= 4 or (r["liked"] or "").strip():
                    report.positive_feedback += 1
                if rating <= 2 or (r["disliked"] or "").strip():
                    report.negative_feedback += 1
    except Exception:
        pass
    if ratings:
        report.avg_rating = sum(ratings) / len(ratings)

    # corrections
    try:
        with mem._conn() as conn:
            q = "SELECT COUNT(*) c FROM corrections WHERE created_at>=?"
            args3: list[Any] = [cutoff]
            if user_id:
                q = "SELECT COUNT(*) c FROM corrections WHERE created_at>=? AND user_id=?"
                args3.append(int(user_id))
            row = conn.execute(q, tuple(args3)).fetchone()
            report.corrections = int(row["c"] if row else 0)
    except Exception:
        pass

    # interaction outcomes for learning velocity
    net = 0
    n_out = 0
    try:
        with mem._conn() as conn:
            rows = conn.execute(
                "SELECT payload_json FROM event_log WHERE event=? AND created_at>=? ORDER BY id DESC LIMIT 500",
                ("interaction_outcome", cutoff),
            ).fetchall()
            for r in rows:
                try:
                    data = json.loads(r["payload_json"] or "{}")
                except Exception:
                    continue
                net += int(data.get("delta") or 0)
                n_out += 1
    except Exception:
        pass
    report.learning_velocity = (net / report.generations) if report.generations else (net / max(1, n_out))

    # Map user → variant for rating attribution
    user_variant: dict[int, str] = {}
    for g in gen_rows:
        uid = g.get("_uid")
        if uid is not None and g.get("ab"):
            user_variant[int(uid)] = str(g["ab"])

    for ab, b in ab_bucket.items():
        n = int(b["n"])
        ok = int(b["ok"])
        report.ab_stats[ab] = {
            "n": n,
            "success_rate": (ok / n) if n else 0.0,
            "avg_rating": None,
            "ratings_n": 0,
        }

    # Attribute feedback ratings to AB via user assignment
    try:
        with mem._conn() as conn:
            q = "SELECT user_id, rating FROM user_feedback WHERE created_at>=?"
            args_f: list[Any] = [cutoff]
            if user_id:
                q += " AND user_id=?"
                args_f.append(int(user_id))
            for r in conn.execute(q + " LIMIT 1000", tuple(args_f)).fetchall():
                uid = int(r["user_id"] or 0)
                rating = int(r["rating"] or 0)
                if not uid or not rating:
                    continue
                ab = user_variant.get(uid) or assign_ab_variant(uid).variant
                st = report.ab_stats.setdefault(
                    ab, {"n": 0, "success_rate": 0.0, "avg_rating": None, "ratings_n": 0}
                )
                st.setdefault("_sum", 0)
                st.setdefault("ratings_n", 0)
                st["_sum"] = int(st.get("_sum") or 0) + rating
                st["ratings_n"] = int(st.get("ratings_n") or 0) + 1
        for ab, st in report.ab_stats.items():
            rn = int(st.get("ratings_n") or 0)
            if rn and st.get("_sum") is not None:
                st["avg_rating"] = round(float(st["_sum"]) / rn, 2)
            st.pop("_sum", None)
    except Exception:
        pass

    # Feature-level success from bots_built
    try:
        feat_ok: dict[str, int] = {}
        feat_n: dict[str, int] = {}
        with mem._conn() as conn:
            brows = conn.execute(
                "SELECT features_json, success, created_at FROM bots_built WHERE created_at>=? ORDER BY created_at DESC LIMIT 500",
                (cutoff,),
            ).fetchall()
            for r in brows:
                try:
                    feats = json.loads(r["features_json"] or "[]")
                except Exception:
                    feats = []
                ok = 1 if r["success"] else 0
                for f in feats:
                    if not isinstance(f, str) or f in {"start", "help", "lang"}:
                        continue
                    feat_n[f] = feat_n.get(f, 0) + 1
                    feat_ok[f] = feat_ok.get(f, 0) + ok
        board = []
        for f, n in feat_n.items():
            if n < 1:
                continue
            board.append(
                {
                    "feature": f,
                    "n": n,
                    "success_rate": (feat_ok.get(f, 0) / n) if n else 0.0,
                }
            )
        board.sort(key=lambda x: (-x["success_rate"], -x["n"]))
        report.feature_leaderboard = board[:12]
    except Exception:
        pass

    # Declare AB winner
    try:
        scored = []
        for ab, st in report.ab_stats.items():
            if ab in {"?", ""}:
                continue
            if int(st.get("n") or 0) < 2:
                continue
            score = float(st.get("success_rate") or 0) * 0.7
            if st.get("avg_rating") is not None:
                score += (float(st["avg_rating"]) / 5.0) * 0.3
            scored.append((ab, score, st))
        if scored:
            scored.sort(key=lambda x: -x[1])
            if len(scored) == 1 or scored[0][1] - scored[1][1] >= 0.05:
                report.ab_winner = scored[0][0]
    except Exception:
        pass

    # notes / recommendations
    if report.generations >= 3 and report.success_rate < 0.5:
        report.notes.append("معدل النجاح منخفض — راجع الـ briefs الفاشلة والـ strict mapping")
    if report.corrections > report.generations * 0.5 and report.generations:
        report.notes.append("تصحيحات كثيرة — حسّن الاستخراج (مرحلة 1) للقوائم والأسماء")
    if report.negative_feedback > report.positive_feedback and report.feedback_count >= 3:
        report.notes.append("تقييمات سلبية أعلى — راجع وصفات النجاح (مرحلة 3)")
    if report.ab_stats.get("A") and report.ab_stats.get("B"):
        a = report.ab_stats["A"].get("success_rate") or 0
        b = report.ab_stats["B"].get("success_rate") or 0
        if abs(a - b) >= 0.15 and min(report.ab_stats["A"]["n"], report.ab_stats["B"]["n"]) >= 3:
            winner = "A" if a > b else "B"
            report.notes.append(f"A/B: المتغير {winner} أفضل نجاحًا حتى الآن")

    return report


def user_feature_stats(
    user_id: int,
    *,
    memory: MemoryEngine | None = None,
    window_hours: float = 168.0,
) -> dict[str, Any]:
    """Per-user feature success from their own bots_built."""
    mem = memory or get_memory_engine()
    if not user_id:
        return {"prefer": [], "avoid": [], "bots": 0, "success_rate": 0.0}
    cutoff = time.time() - float(window_hours) * 3600.0
    feat_ok: dict[str, int] = {}
    feat_n: dict[str, int] = {}
    bots = 0
    ok_bots = 0
    try:
        with mem._conn() as conn:
            rows = conn.execute(
                "SELECT features_json, success, created_at FROM bots_built "
                "WHERE user_id=? AND created_at>=? ORDER BY created_at DESC LIMIT 100",
                (int(user_id), cutoff),
            ).fetchall()
            for r in rows:
                bots += 1
                if r["success"]:
                    ok_bots += 1
                try:
                    feats = json.loads(r["features_json"] or "[]")
                except Exception:
                    feats = []
                for f in feats:
                    if not isinstance(f, str) or f in {"start", "help", "lang"}:
                        continue
                    feat_n[f] = feat_n.get(f, 0) + 1
                    feat_ok[f] = feat_ok.get(f, 0) + (1 if r["success"] else 0)
    except Exception:
        pass
    prefer, avoid = [], []
    for f, n in feat_n.items():
        rate = feat_ok.get(f, 0) / n if n else 0.0
        if n >= 1 and rate >= 0.67:
            prefer.append(f)
        if n >= 1 and rate <= 0.34:
            avoid.append(f)
    return {
        "prefer": prefer[:10],
        "avoid": avoid[:10],
        "bots": bots,
        "success_rate": (ok_bots / bots) if bots else 0.0,
    }


def apply_eval_to_features(
    features: list[str],
    user_id: int | None,
    *,
    strict: bool = False,
    memory: MemoryEngine | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Closed-loop: merge global + user prefer/avoid into feature list.

    strict: only DROP user/global avoid for non-core experimental features.
    non-strict: also ADD prefers.
    """
    core = {"start", "help", "lang", "shop_catalog", "order_track", "pay_methods", "ticket_open", "faq_show"}
    out = list(dict.fromkeys(features or []))
    tw = recommend_generation_tweaks(user_id, memory=memory)
    user = user_feature_stats(int(user_id), memory=memory) if user_id else {"prefer": [], "avoid": []}
    avoid = set(tw.get("avoid_features") or []) | set(user.get("avoid") or [])
    prefer = list(dict.fromkeys(list(tw.get("prefer_features") or []) + list(user.get("prefer") or [])))

    dropped = [f for f in out if f in avoid and f not in core]
    out = [f for f in out if f not in set(dropped)]
    added = []
    if not strict:
        for f in prefer:
            if f not in out:
                out.append(f)
                added.append(f)
            if len(added) >= 5:
                break
    meta = {
        "dropped": dropped[:10],
        "added": added[:10],
        "user_success_rate": user.get("success_rate"),
        "ab_winner": tw.get("ab_winner"),
        "prefer": prefer[:8],
        "avoid": list(avoid)[:8],
    }
    return list(dict.fromkeys(out)), meta


def recommend_generation_tweaks(
    user_id: int | None = None,
    *,
    memory: MemoryEngine | None = None,
    window_hours: float = 72.0,
) -> dict[str, Any]:
    """Actionable tweaks for generation path from Stage-5 analytics."""
    rep = build_performance_report(
        window_hours=window_hours, memory=memory, user_id=None
    )
    tweaks: dict[str, Any] = {
        "prefer_features": [],
        "avoid_features": [],
        "ab_winner": rep.ab_winner,
        "force_variant": None,
        "notes": list(rep.notes[:4]),
    }
    for item in rep.feature_leaderboard[:6]:
        if float(item.get("success_rate") or 0) >= 0.7 and int(item.get("n") or 0) >= 2:
            tweaks["prefer_features"].append(item["feature"])
        if float(item.get("success_rate") or 0) <= 0.35 and int(item.get("n") or 0) >= 2:
            tweaks["avoid_features"].append(item["feature"])
    # Optionally bias new users toward winner after enough samples
    if rep.ab_winner and rep.generations >= 8:
        total_n = sum(int(st.get("n") or 0) for st in rep.ab_stats.values())
        if total_n >= 8:
            tweaks["force_variant"] = None  # keep stable assignment; expose winner only
    return tweaks


def is_eval_command(text: str) -> bool:
    t = (text or "").strip().lower()
    keys = (
        "/eval", "/stats", "/performance", "تقرير", "إحصائيات", "احصائيات",
        "تقييم النظام", "أداء البوت", "performance",
    )
    return t in keys or any(t == k for k in keys)


__all__ = [
    "AB_VARIANTS",
    "ABAssignment",
    "PerformanceReport",
    "assign_ab_variant",
    "get_ab_config",
    "apply_ab_to_narrative",
    "record_generation_outcome",
    "record_ab_exposure",
    "build_performance_report",
    "is_eval_command",
    "recommend_generation_tweaks",
    "user_feature_stats",
]
