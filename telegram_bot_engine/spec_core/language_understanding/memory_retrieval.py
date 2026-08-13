"""MemoryEngine responsibility mixins.

These modules contain persistence, retrieval, and session behavior while
`memory_engine.py` remains the backward-compatible public facade.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .memory_engine import (
    BuiltBotRecord,
    IntentAnalysis,
    LanguageUnderstandingResult,
    SessionMemory,
    UserProfile,
    _DURABLE_SLOTS,
    _clip,
    _default_db_path,
    _now,
)

class MemoryRetrievalMixin:
    def find_similar_briefs(self, request_text: str, *, limit: int = 5) -> list[dict]:

            """Similarity via normalized token overlap (Arabic-aware)."""

            try:

                from .normalize import normalize_text, tokenize

                q = set(tokenize(normalize_text(request_text or "")))

            except Exception:

                q = set(w for w in (request_text or "").lower().split() if len(w) > 2)

            # also raw lowercase tokens for latin keys

            q |= set(w for w in (request_text or "").lower().replace("_", " ").split() if len(w) > 2)

            if not q:

                return []

            out: list[dict] = []

            try:

                with self._conn() as conn:

                    try:

                        rows = conn.execute(

                            "SELECT bot_name, purpose, features_json, menu_json, request_text, tokens "

                            "FROM brief_index ORDER BY id DESC LIMIT 300"

                        ).fetchall()

                    except Exception:

                        rows = []

                    for r in rows:

                        blob = " ".join(

                            str(x or "")

                            for x in (r["tokens"], r["request_text"], r["purpose"], r["bot_name"], r["features_json"])

                        )

                        try:

                            from .normalize import normalize_text, tokenize

                            tokens = set(tokenize(normalize_text(blob)))

                        except Exception:

                            tokens = set(w for w in blob.lower().split() if len(w) > 2)

                        tokens |= set(w for w in blob.lower().replace("_", " ").split() if len(w) > 2)

                        if not tokens:

                            continue

                        inter = len(q & tokens)

                        if inter <= 0:

                            continue

                        union = len(q | tokens)

                        score = inter / union if union else 0.0

                        # boost shared purpose words

                        if inter >= 2:

                            score += 0.05 * min(inter, 5)

                        if score < 0.05:

                            continue

                        try:

                            feats = json.loads(r["features_json"] or "[]")

                        except Exception:

                            feats = []

                        out.append(

                            {

                                "bot_name": r["bot_name"],

                                "purpose": r["purpose"],

                                "features": feats if isinstance(feats, list) else [],

                                "score": round(min(score, 1.0), 3),

                                "request": (r["request_text"] or "")[:120],

                            }

                        )

                    try:

                        brows = conn.execute(

                            "SELECT name, intent, features_json, request_text FROM bots_built "

                            "WHERE success=1 ORDER BY created_at DESC LIMIT 150"

                        ).fetchall()

                    except Exception:

                        brows = []

                    for r in brows:

                        blob = " ".join(str(x or "") for x in (r["request_text"], r["name"], r["intent"], r["features_json"]))

                        try:

                            from .normalize import normalize_text, tokenize

                            tokens = set(tokenize(normalize_text(blob)))

                        except Exception:

                            tokens = set(w for w in blob.lower().split() if len(w) > 2)

                        tokens |= set(w for w in blob.lower().replace("_", " ").split() if len(w) > 2)

                        inter = len(q & tokens)

                        if inter <= 0:

                            continue

                        union = len(q | tokens)

                        score = inter / union if union else 0.0

                        if inter >= 2:

                            score += 0.05 * min(inter, 5)

                        if score < 0.05:

                            continue

                        try:

                            feats = json.loads(r["features_json"] or "[]")

                        except Exception:

                            feats = []

                        out.append(

                            {

                                "bot_name": r["name"],

                                "purpose": r["intent"],

                                "features": feats if isinstance(feats, list) else [],

                                "score": round(min(score, 1.0), 3),

                                "request": (r["request_text"] or "")[:120],

                            }

                        )

            except Exception:

                return []

            out.sort(key=lambda x: -float(x.get("score") or 0))

            seen: set[str] = set()

            deduped = []

            for item in out:

                key = str(item.get("bot_name") or "") + "|" + str(item.get("request") or "")[:40]

                if key in seen:

                    continue

                seen.add(key)

                deduped.append(item)

                if len(deduped) >= limit:

                    break

            return deduped

    def record_patterns(

            self,

            *,

            intent: str | None,

            features: list[str] | None = None,

            skill: str | None = None,

            text: str | None = None,

        ) -> None:

            if not intent:

                return

            feats = list(features or [])

            with self._lock:

                with self._conn() as conn:

                    conn.execute(

                        """

                        INSERT INTO pattern_intent(intent, total) VALUES(?,1)

                        ON CONFLICT(intent) DO UPDATE SET total=total+1

                        """,

                        (intent,),

                    )

                    for f in feats[:40]:

                        conn.execute(

                            """

                            INSERT INTO pattern_cooccur(intent, feature, count) VALUES(?,?,1)

                            ON CONFLICT(intent, feature) DO UPDATE SET count=count+1

                            """,

                            (intent, f),

                        )

                    conn.commit()

    def top_features_for_intent(self, intent: str, *, limit: int = 8) -> list[tuple[str, float]]:

            with self._lock:

                with self._conn() as conn:

                    row = conn.execute(

                        "SELECT total FROM pattern_intent WHERE intent=?", (intent,)

                    ).fetchone()

                    total = int(row["total"]) if row else 0

                    if total <= 0:

                        return []

                    rows = conn.execute(

                        """

                        SELECT feature, count FROM pattern_cooccur

                        WHERE intent=? ORDER BY count DESC LIMIT ?

                        """,

                        (intent, int(limit)),

                    ).fetchall()

            return [(r["feature"], round(int(r["count"]) / total, 3)) for r in rows]

    def top_slot_values(self, intent: str, slot: str, *, limit: int = 5) -> list[tuple[str, int]]:

            with self._lock:

                with self._conn() as conn:

                    rows = conn.execute(

                        """

                        SELECT value, count FROM pattern_slot

                        WHERE intent=? AND slot=? ORDER BY count DESC LIMIT ?

                        """,

                        (intent, slot, int(limit)),

                    ).fetchall()

            return [(r["value"], int(r["count"])) for r in rows]

    def suggest_features(

            self, intent: str, *, already: list[str] | None = None, min_p: float = 0.35

        ) -> list[dict[str, Any]]:

            already_set = set(already or [])

            out = []

            for feat, p in self.top_features_for_intent(intent, limit=15):

                if feat in already_set or p < min_p:

                    continue

                out.append({"feature": feat, "probability": p})

            return out

    def recall_known(self, user_id: int, *, session_id: str = "default") -> dict[str, Any]:

            """Iron merge: durable prefs ∪ session answers (session wins on conflict)."""

            profile = self.get_user(user_id)

            known: dict[str, Any] = {}

            # durable first

            for k, v in (profile.durable_slots or {}).items():

                if v not in (None, "", []):

                    known[k] = v

            if profile.default_payments and "payment" not in known:

                known["payment"] = list(profile.default_payments)

            if profile.default_wants_delivery is True:

                known.setdefault("delivery", True)

            if profile.default_wants_discounts is True:

                known.setdefault("discounts", True)

            if profile.language_preference:

                known.setdefault("language_ui", profile.language_preference)

            # session overrides

            sess = self.get_session(user_id, session_id)

            for k, v in (sess.answers or {}).items():

                if v not in (None, ""):

                    known[k] = v

            return known

    def prefer_user_defaults(self, user_id: int, feature_plan: list[str]) -> list[str]:

            profile = self.get_user(user_id)

            out = list(feature_plan)

            for f in profile.preferred_features:

                if f not in out:

                    out.append(f)

            return out[:60]

    def continuity_hint(self, user_id: int) -> str:

            """Short Arabic/English hint for returning users."""

            profile = self.get_user(user_id)

            last = self.last_bot(user_id)

            if last:

                if profile.language_preference == "en":

                    return f"Welcome back — last bot: {last.get('name')} ({last.get('intent')})."

                return f"مرحباً بعودتك — آخر بوت: {last.get('name')} ({last.get('intent')})."

            if profile.favorite_intents:

                top = profile.favorite_intents[0]

                if profile.language_preference == "en":

                    return f"You often build: {top}."

                return f"غالباً بتبني بوتات: {top}."

            return ""
