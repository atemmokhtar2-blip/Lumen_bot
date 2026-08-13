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

class MemoryStoreMixin:
    def _conn(self) -> sqlite3.Connection:

            c = sqlite3.connect(str(self.path), timeout=60, check_same_thread=False)

            c.row_factory = sqlite3.Row

            try:

                c.execute("PRAGMA journal_mode=WAL")

                c.execute("PRAGMA synchronous=NORMAL")

            except Exception:

                pass

            return c

    def _init(self) -> None:

            with self._lock:

                with self._conn() as conn:

                    conn.executescript(

                        """

                        CREATE TABLE IF NOT EXISTS user_profiles (

                            user_id INTEGER PRIMARY KEY,

                            data_json TEXT NOT NULL DEFAULT '{}',

                            updated_at REAL NOT NULL

                        );

                        CREATE TABLE IF NOT EXISTS session_memory (

                            user_id INTEGER NOT NULL,

                            session_id TEXT NOT NULL,

                            data_json TEXT NOT NULL DEFAULT '{}',

                            updated_at REAL NOT NULL,

                            PRIMARY KEY (user_id, session_id)

                        );

                        CREATE TABLE IF NOT EXISTS interaction_ledger (

                            id INTEGER PRIMARY KEY AUTOINCREMENT,

                            user_id INTEGER NOT NULL,

                            text TEXT,

                            intent TEXT,

                            confidence REAL,

                            features_json TEXT,

                            success INTEGER,

                            session_id TEXT,

                            created_at REAL NOT NULL

                        );

                        CREATE INDEX IF NOT EXISTS idx_ledger_user ON interaction_ledger(user_id, created_at DESC);

                        CREATE TABLE IF NOT EXISTS bots_built (

                            bot_id TEXT PRIMARY KEY,

                            user_id INTEGER NOT NULL,

                            name TEXT,

                            intent TEXT,

                            features_json TEXT,

                            request_text TEXT,

                            preset TEXT,

                            output_path TEXT,

                            success INTEGER,

                            meta_json TEXT,

                            created_at REAL NOT NULL

                        );

                        CREATE INDEX IF NOT EXISTS idx_bots_user ON bots_built(user_id, created_at DESC);

                        CREATE TABLE IF NOT EXISTS pattern_intent (

                            intent TEXT PRIMARY KEY,

                            total INTEGER NOT NULL DEFAULT 0

                        );

                        CREATE TABLE IF NOT EXISTS pattern_cooccur (

                            intent TEXT NOT NULL,

                            feature TEXT NOT NULL,

                            count INTEGER NOT NULL DEFAULT 0,

                            PRIMARY KEY (intent, feature)

                        );

                        CREATE TABLE IF NOT EXISTS pattern_slot (

                            intent TEXT NOT NULL,

                            slot TEXT NOT NULL,

                            value TEXT NOT NULL,

                            count INTEGER NOT NULL DEFAULT 0,

                            PRIMARY KEY (intent, slot, value)

                        );

                        CREATE TABLE IF NOT EXISTS user_feedback (

                            id INTEGER PRIMARY KEY AUTOINCREMENT,

                            user_id INTEGER,

                            bot_id TEXT,

                            rating INTEGER,

                            liked TEXT,

                            disliked TEXT,

                            created_at REAL NOT NULL

                        );

                        CREATE TABLE IF NOT EXISTS event_log (

                            id INTEGER PRIMARY KEY AUTOINCREMENT,

                            user_id INTEGER,

                            event TEXT,

                            payload_json TEXT,

                            created_at REAL NOT NULL

                        );

                        """

                    )

                    conn.commit()

    def _event(self, user_id: int | None, event: str, payload: dict[str, Any] | None = None) -> None:

            try:

                with self._conn() as conn:

                    conn.execute(

                        "INSERT INTO event_log(user_id, event, payload_json, created_at) VALUES(?,?,?,?)",

                        (

                            int(user_id) if user_id is not None else None,

                            event,

                            json.dumps(payload or {}, ensure_ascii=False, default=str)[:2000],

                            _now(),

                        ),

                    )

                    conn.commit()

            except Exception:

                pass

    def get_user(self, user_id: int) -> UserProfile:

            with self._lock:

                with self._conn() as conn:

                    row = conn.execute(

                        "SELECT data_json FROM user_profiles WHERE user_id=?",

                        (int(user_id),),

                    ).fetchone()

            if not row:

                return UserProfile(user_id=int(user_id))

            try:

                data = json.loads(row["data_json"] or "{}")

            except Exception:

                data = {}

            return UserProfile.from_dict(int(user_id), data if isinstance(data, dict) else {})

    def save_user(self, profile: UserProfile) -> None:

            profile.updated_at = _now()

            payload = json.dumps(profile.to_dict(), ensure_ascii=False, default=str)

            with self._lock:

                with self._conn() as conn:

                    conn.execute(

                        """

                        INSERT INTO user_profiles(user_id, data_json, updated_at)

                        VALUES(?,?,?)

                        ON CONFLICT(user_id) DO UPDATE SET

                            data_json=excluded.data_json,

                            updated_at=excluded.updated_at

                        """,

                        (int(profile.user_id), payload, profile.updated_at),

                    )

                    conn.commit()

    def set_durable_slot(self, user_id: int, slot: str, value: Any) -> UserProfile:

            profile = self.get_user(user_id)

            slot = str(slot)

            profile.durable_slots[slot] = value

            # mirror common commerce defaults

            if slot == "payment":

                if isinstance(value, list):

                    profile.default_payments = list(value)

                elif isinstance(value, str):

                    profile.default_payments = [value]

            if slot == "delivery":

                profile.default_wants_delivery = bool(value) if value not in ("لا", "no", "0", False) else False

            if slot == "discounts":

                profile.default_wants_discounts = bool(value) if value not in ("لا", "no", "0", False) else False

            if slot == "language_ui":

                if str(value).lower() in {"en", "english", "انجليزي"}:

                    profile.language_preference = "en"

                elif str(value).lower() in {"ar", "عربي", "arabic"}:

                    profile.language_preference = "ar"

            self.save_user(profile)

            self._event(user_id, "durable_slot", {"slot": slot, "value": value})

            return profile

    def update_user_from_analysis(

            self,

            user_id: int,

            *,

            text: str,

            intent: IntentAnalysis | None = None,

            lu: LanguageUnderstandingResult | None = None,

            features_accepted: list[str] | None = None,

            success: bool | None = None,

        ) -> UserProfile:

            profile = self.get_user(user_id)

            if intent:

                order = {"beginner": 0, "intermediate": 1, "expert": 2}

                cur = order.get(profile.skill_level, 0)

                got = order.get(intent.skill_level, 0)

                if got > cur:

                    profile.skill_level = intent.skill_level

                elif got < cur and profile.total_builds < 2:

                    profile.skill_level = intent.skill_level

                if intent.language.startswith("ar"):

                    profile.language_preference = "ar" if intent.language != "mixed" else "mixed"

                elif intent.language == "en":

                    profile.language_preference = "en"

                if intent.complexity:

                    # ratchet complexity preference toward what user actually requests

                    cmap = {"simple": 0, "medium": 1, "complex": 2}

                    if cmap.get(intent.complexity, 0) >= cmap.get(profile.complexity_preference, 0):

                        profile.complexity_preference = intent.complexity

                if intent.primary:

                    name = intent.primary.intent

                    fav = list(profile.favorite_intents)

                    if name in fav:

                        fav.remove(name)

                    fav.insert(0, name)

                    profile.favorite_intents = fav[:15]

                    if success:

                        profile.bot_types_built = list(

                            dict.fromkeys(profile.bot_types_built + [name])

                        )[:25]

                # Learn durable slots from entities automatically

                if lu and lu.entities:

                    ent = lu.entities

                    if ent.payment_methods:

                        profile.default_payments = list(

                            dict.fromkeys(list(ent.payment_methods) + profile.default_payments)

                        )[:8]

                        profile.durable_slots["payment"] = profile.default_payments

                    if ent.wants_delivery:

                        profile.default_wants_delivery = True

                        profile.durable_slots["delivery"] = True

                    if ent.wants_discounts:

                        profile.default_wants_discounts = True

                        profile.durable_slots["discounts"] = True

                    if ent.product or (ent.category and ent.category not in {"أمن سيبراني", "دورات"}):

                        profile.durable_slots.setdefault(

                            "product_or_category", ent.product or ent.category

                        )

                if features_accepted:

                    profile.preferred_features = list(

                        dict.fromkeys(list(features_accepted) + profile.preferred_features)

                    )[:50]

                elif intent.feature_plan:

                    profile.preferred_features = list(

                        dict.fromkeys(profile.preferred_features + list(intent.feature_plan)[:8])

                    )[:50]



            if text:

                ar = len(re.findall(r"[\u0600-\u06FF]", text))

                en = len(re.findall(r"[A-Za-z]", text))

                if ar and en:

                    profile.naming_style = "mixed"

                elif ar:

                    profile.naming_style = "ar"

                elif en:

                    profile.naming_style = "en"



            interaction = {

                "text": _clip(text, 300),

                "intent": intent.primary.intent if intent and intent.primary else None,

                "ts": _now(),

                "success": success,

            }

            profile.last_interactions = (profile.last_interactions + [interaction])[-8:]

            if success:

                profile.total_builds += 1

            self.save_user(profile)



            # ledger row

            try:

                with self._lock:

                    with self._conn() as conn:

                        conn.execute(

                            """

                            INSERT INTO interaction_ledger(

                                user_id, text, intent, confidence, features_json, success, session_id, created_at

                            ) VALUES(?,?,?,?,?,?,?,?)

                            """,

                            (

                                int(user_id),

                                _clip(text, 500),

                                intent.primary.intent if intent and intent.primary else None,

                                float(intent.primary.confidence) if intent and intent.primary else None,

                                json.dumps(

                                    (features_accepted or (intent.feature_plan if intent else []) or [])[:40],

                                    ensure_ascii=False,

                                ),

                                1 if success else (0 if success is False else None),

                                None,

                                _now(),

                            ),

                        )

                        conn.commit()

            except Exception:

                pass

            return profile

    def add_pain_point(self, user_id: int, note: str) -> None:

            profile = self.get_user(user_id)

            note = _clip(note, 200)

            if note and note not in profile.pain_points:

                profile.pain_points = (profile.pain_points + [note])[-20:]

                self.save_user(profile)

    def history(self, user_id: int, *, limit: int = 20) -> list[dict[str, Any]]:

            with self._lock:

                with self._conn() as conn:

                    rows = conn.execute(

                        """

                        SELECT text, intent, confidence, features_json, success, created_at

                        FROM interaction_ledger WHERE user_id=?

                        ORDER BY id DESC LIMIT ?

                        """,

                        (int(user_id), int(limit)),

                    ).fetchall()

            out = []

            for r in rows:

                feats = []

                try:

                    feats = json.loads(r["features_json"] or "[]")

                except Exception:

                    pass

                out.append(

                    {

                        "text": r["text"],

                        "intent": r["intent"],

                        "confidence": r["confidence"],

                        "features": feats,

                        "success": r["success"],

                        "created_at": r["created_at"],

                    }

                )

            return out

    def store_bot_brief(self, user_id: int, brief: dict, request_text: str = "") -> None:

            """Remember the structured brief so generation/corrections stay aligned."""

            if not user_id or not brief:

                return

            payload = {

                "brief": brief,

                "request": (request_text or "")[:500],

            }

            self._event(int(user_id), "bot_brief", payload)

            try:

                feats = brief.get("features_requested") or brief.get("action_ids") or []

                menu = brief.get("action_ids") or []

                tokens = " ".join(

                    str(x) for x in (

                        [brief.get("bot_name"), brief.get("purpose")]

                        + list(feats)[:20]

                        + list(menu)[:10]

                        + (request_text or "").split()[:30]

                    ) if x

                )

                with self._lock:

                    with self._conn() as conn:

                        try:

                            conn.execute(

                                "CREATE TABLE IF NOT EXISTS brief_index ("

                                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, bot_name TEXT, "

                                "purpose TEXT, features_json TEXT, menu_json TEXT, request_text TEXT, "

                                "tokens TEXT, created_at REAL NOT NULL)"

                            )

                        except Exception:

                            pass

                        conn.execute(

                            "INSERT INTO brief_index(user_id, bot_name, purpose, features_json, menu_json, request_text, tokens, created_at) "

                            "VALUES (?,?,?,?,?,?,?,?)",

                            (

                                int(user_id),

                                str(brief.get("bot_name") or "")[:80],

                                str(brief.get("purpose") or "")[:40],

                                json.dumps(list(feats)[:30], ensure_ascii=False),

                                json.dumps(list(menu)[:20], ensure_ascii=False),

                                (request_text or "")[:500],

                                tokens[:800],

                                _now(),

                            ),

                        )

                        conn.commit()

            except Exception:

                pass

            # also stash on session for same-turn use

            try:

                sid = "default"

                sm = self.get_session(int(user_id), sid)

                answers = dict(getattr(sm, "answers", None) or {})

                answers["_bot_brief"] = brief

                # re-save session answers if API allows

                with self._lock:

                    with self._conn() as conn:

                        row = conn.execute(

                            "SELECT data_json FROM session_memory WHERE user_id=? AND session_id=?",

                            (int(user_id), sid),

                        ).fetchone()

                        import json as _json

                        data = {}

                        if row and row[0]:

                            try:

                                data = _json.loads(row[0])

                            except Exception:

                                data = {}

                        data["answers"] = answers

                        data["updated_at"] = _now()

                        conn.execute(

                            "INSERT INTO session_memory(user_id, session_id, data_json, updated_at) VALUES(?,?,?,?) "

                            "ON CONFLICT(user_id, session_id) DO UPDATE SET data_json=excluded.data_json, updated_at=excluded.updated_at",

                            (int(user_id), sid, _json.dumps(data, ensure_ascii=False, default=str), _now()),

                        )

                        conn.commit()

            except Exception:

                pass

    def last_bot_brief(self, user_id: int) -> dict | None:

            """Most recent bot_brief event for this user."""

            if not user_id:

                return None

            try:

                with self._conn() as conn:

                    row = conn.execute(

                        "SELECT payload_json FROM event_log WHERE user_id=? AND event=? ORDER BY id DESC LIMIT 1",

                        (int(user_id), "bot_brief"),

                    ).fetchone()

                if not row or not row[0]:

                    return None

                import json as _json

                data = _json.loads(row[0])

                return data.get("brief") if isinstance(data, dict) else None

            except Exception:

                return None

    def record_correction(

            self,

            user_id: int,

            *,

            rejected: str = "",

            preferred: str = "",

            context: str = "",

        ) -> None:

            if not user_id:

                return

            with self._lock:

                with self._conn() as conn:

                    try:

                        conn.execute(

                            "INSERT INTO corrections(user_id, rejected, preferred, context, created_at) VALUES (?,?,?,?,?)",

                            (

                                int(user_id),

                                (rejected or "")[:120],

                                (preferred or "")[:200],

                                (context or "")[:400],

                                _now(),

                            ),

                        )

                        conn.commit()

                    except Exception:

                        # table may not exist on old DBs — create once

                        try:

                            conn.execute(

                                "CREATE TABLE IF NOT EXISTS corrections ("

                                "id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, "

                                "rejected TEXT, preferred TEXT, context TEXT, created_at REAL NOT NULL)"

                            )

                            conn.execute(

                                "INSERT INTO corrections(user_id, rejected, preferred, context, created_at) VALUES (?,?,?,?,?)",

                                (int(user_id), (rejected or "")[:120], (preferred or "")[:200], (context or "")[:400], _now()),

                            )

                            conn.commit()

                        except Exception:

                            pass

            self._event(int(user_id), "correction", {"rejected": rejected, "preferred": preferred})

    def list_corrections(self, user_id: int, *, limit: int = 10) -> list[dict]:

            if not user_id:

                return []

            try:

                with self._conn() as conn:

                    rows = conn.execute(

                        "SELECT rejected, preferred, context, created_at FROM corrections "

                        "WHERE user_id=? ORDER BY id DESC LIMIT ?",

                        (int(user_id), int(limit)),

                    ).fetchall()

                return [

                    {

                        "rejected": r["rejected"],

                        "preferred": r["preferred"],

                        "context": r["context"],

                        "created_at": r["created_at"],

                    }

                    for r in rows

                ]

            except Exception:

                return []

    def register_bot(

            self,

            user_id: int,

            *,

            name: str,

            intent: str,

            features: list[str] | None = None,

            request_text: str = "",

            preset: str | None = None,

            output_path: str = "",

            success: bool = True,

            meta: dict[str, Any] | None = None,

            bot_id: str | None = None,

        ) -> BuiltBotRecord:

            rec = BuiltBotRecord(

                bot_id=bot_id or uuid.uuid4().hex[:16],

                user_id=int(user_id),

                name=(name or "bot")[:80],

                intent=(intent or "custom")[:40],

                features=list(features or [])[:60],

                request_text=_clip(request_text, 500),

                preset=preset,

                output_path=(output_path or "")[:300],

                success=bool(success),

                created_at=_now(),

                meta=dict(meta or {}),

            )

            with self._lock:

                with self._conn() as conn:

                    conn.execute(

                        """

                        INSERT OR REPLACE INTO bots_built(

                            bot_id, user_id, name, intent, features_json, request_text,

                            preset, output_path, success, meta_json, created_at

                        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)

                        """,

                        (

                            rec.bot_id,

                            rec.user_id,

                            rec.name,

                            rec.intent,

                            json.dumps(rec.features, ensure_ascii=False),

                            rec.request_text,

                            rec.preset,

                            rec.output_path,

                            1 if rec.success else 0,

                            json.dumps(rec.meta, ensure_ascii=False, default=str)[:2000],

                            rec.created_at,

                        ),

                    )

                    conn.commit()

            # update profile

            profile = self.get_user(user_id)

            if rec.intent and rec.intent not in profile.bot_types_built:

                profile.bot_types_built = (profile.bot_types_built + [rec.intent])[:25]

            if rec.features:

                profile.preferred_features = list(

                    dict.fromkeys(rec.features + profile.preferred_features)

                )[:50]

            if success:

                profile.total_builds += 1

            self.save_user(profile)

            self._event(user_id, "bot_registered", {"bot_id": rec.bot_id, "intent": rec.intent})

            return rec

    def list_bots(self, user_id: int, *, limit: int = 20) -> list[dict[str, Any]]:

            with self._lock:

                with self._conn() as conn:

                    rows = conn.execute(

                        """

                        SELECT bot_id, name, intent, features_json, request_text, preset,

                               output_path, success, created_at

                        FROM bots_built WHERE user_id=? ORDER BY created_at DESC LIMIT ?

                        """,

                        (int(user_id), int(limit)),

                    ).fetchall()

            out = []

            for r in rows:

                try:

                    feats = json.loads(r["features_json"] or "[]")

                except Exception:

                    feats = []

                out.append(

                    {

                        "bot_id": r["bot_id"],

                        "name": r["name"],

                        "intent": r["intent"],

                        "features": feats,

                        "request_text": r["request_text"],

                        "preset": r["preset"],

                        "output_path": r["output_path"],

                        "success": bool(r["success"]),

                        "created_at": r["created_at"],

                    }

                )

            return out

    def last_bot(self, user_id: int) -> dict[str, Any] | None:

            bots = self.list_bots(user_id, limit=1)

            return bots[0] if bots else None
