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

class MemorySessionMixin:
    def get_session(self, user_id: int, session_id: str = "default") -> SessionMemory:

            with self._lock:

                with self._conn() as conn:

                    row = conn.execute(

                        "SELECT data_json FROM session_memory WHERE user_id=? AND session_id=?",

                        (int(user_id), str(session_id)),

                    ).fetchone()

            if not row:

                return SessionMemory(

                    user_id=int(user_id), session_id=str(session_id), started_at=_now()

                )

            try:

                data = json.loads(row["data_json"] or "{}")

            except Exception:

                data = {}

            return SessionMemory.from_dict(

                int(user_id), str(session_id), data if isinstance(data, dict) else {}

            )

    def save_session(self, session: SessionMemory) -> None:

            session.updated_at = _now()

            if not session.started_at:

                session.started_at = session.updated_at

            session.utterances = session.utterances[-50:]

            session.questions_asked = session.questions_asked[-60:]

            session.edits = session.edits[-60:]

            payload = json.dumps(session.to_dict(), ensure_ascii=False, default=str)

            with self._lock:

                with self._conn() as conn:

                    conn.execute(

                        """

                        INSERT INTO session_memory(user_id, session_id, data_json, updated_at)

                        VALUES(?,?,?,?)

                        ON CONFLICT(user_id, session_id) DO UPDATE SET

                            data_json=excluded.data_json,

                            updated_at=excluded.updated_at

                        """,

                        (int(session.user_id), str(session.session_id), payload, session.updated_at),

                    )

                    conn.commit()

    def append_utterance(

            self,

            user_id: int,

            text: str,

            *,

            session_id: str = "default",

            intent: IntentAnalysis | None = None,

            understood: dict[str, Any] | None = None,

        ) -> SessionMemory:

            sess = self.get_session(user_id, session_id)

            if text:

                sess.utterances.append(_clip(text, 1000))

            if intent:

                sess.primary_intent = (

                    intent.primary.intent if intent.primary else sess.primary_intent

                )

                sess.feature_plan = list(intent.feature_plan or sess.feature_plan)

                sess.understood = {

                    **sess.understood,

                    "intent": intent.to_dict() if hasattr(intent, "to_dict") else {},

                    **(understood or {}),

                }

                sess.state = "clarifying" if intent.should_ask else "ready"

            elif understood:

                sess.understood = {**sess.understood, **understood}

            self.save_session(sess)

            return sess

    def record_questions(

            self, user_id: int, questions: list[dict[str, Any]], *, session_id: str = "default"

        ) -> SessionMemory:

            sess = self.get_session(user_id, session_id)

            for q in questions:

                sess.questions_asked.append({"q": q, "ts": _now()})

            if questions:

                sess.state = "clarifying"

            self.save_session(sess)

            return sess

    def record_answer(

            self, user_id: int, slot: str, answer: str, *, session_id: str = "default", promote: bool = True

        ) -> SessionMemory:

            sess = self.get_session(user_id, session_id)

            sess.answers[str(slot)] = answer

            sess.edits.append({"slot": slot, "answer": answer, "ts": _now()})

            self.save_session(sess)

            # Iron memory: promote to durable user prefs

            if promote and slot in _DURABLE_SLOTS:

                val: Any = answer

                # normalize payment answers

                if slot == "payment":

                    low = (answer or "").lower()

                    mapped = []

                    for name, keys in (

                        ("visa", ("فيزا", "visa", "card", "stripe")),

                        ("vodafone_cash", ("فودافون", "vodafone")),

                        ("fawry", ("فوري", "fawry")),

                        ("wallet", ("محفظ", "wallet")),

                        ("cod", ("استلام", "cod")),

                        ("paypal", ("paypal", "باي")),

                    ):

                        if any(k in low for k in keys):

                            mapped.append(name)

                    if mapped:

                        val = mapped

                self.set_durable_slot(user_id, slot, val)

                # slot patterns

                try:

                    intent = sess.primary_intent or "generic"

                    with self._lock:

                        with self._conn() as conn:

                            conn.execute(

                                """

                                INSERT INTO pattern_slot(intent, slot, value, count)

                                VALUES(?,?,?,1)

                                ON CONFLICT(intent, slot, value) DO UPDATE SET count=count+1

                                """,

                                (intent, str(slot), _clip(str(answer), 80)),

                            )

                            conn.commit()

                except Exception:

                    pass

            return sess

    def set_session_state(self, user_id: int, state: str, *, session_id: str = "default") -> None:

            sess = self.get_session(user_id, session_id)

            sess.state = state

            self.save_session(sess)

    def clear_session(self, user_id: int, session_id: str = "default") -> None:

            with self._lock:

                with self._conn() as conn:

                    conn.execute(

                        "DELETE FROM session_memory WHERE user_id=? AND session_id=?",

                        (int(user_id), str(session_id)),

                    )

                    conn.commit()

    def record_feedback(

            self,

            user_id: int,

            *,

            rating: int,

            liked: str = "",

            disliked: str = "",

            bot_id: str = "",

        ) -> None:

            with self._lock:

                with self._conn() as conn:

                    conn.execute(

                        """

                        INSERT INTO user_feedback(user_id, bot_id, rating, liked, disliked, created_at)

                        VALUES(?,?,?,?,?,?)

                        """,

                        (

                            int(user_id),

                            bot_id or "",

                            int(rating),

                            _clip(liked, 300),

                            _clip(disliked, 300),

                            _now(),

                        ),

                    )

                    conn.commit()

            if disliked:

                self.add_pain_point(user_id, disliked)

    def remember_turn(

            self,

            user_id: int,

            text: str,

            *,

            intent: IntentAnalysis | None = None,

            lu: LanguageUnderstandingResult | None = None,

            questions: list[dict[str, Any]] | None = None,

            session_id: str = "default",

            success: bool | None = None,

            features: list[str] | None = None,

        ) -> dict[str, Any]:

            profile = self.update_user_from_analysis(

                user_id,

                text=text,

                intent=intent,

                lu=lu,

                features_accepted=features,

                success=success,

            )

            sess = self.append_utterance(

                user_id,

                text,

                session_id=session_id,

                intent=intent,

                understood={"lu": lu.to_dict() if lu and hasattr(lu, "to_dict") else {}},

            )

            if questions:

                self.record_questions(user_id, questions, session_id=session_id)

            if intent and intent.primary:

                self.record_patterns(

                    intent=intent.primary.intent,

                    features=features or intent.feature_plan,

                    skill=intent.skill_level,

                    text=text,

                )

            return {

                "profile": profile.to_dict(),

                "session": sess.to_dict(),

                "known": self.recall_known(user_id, session_id=session_id),

                "suggestions": self.suggest_features(

                    intent.primary.intent,

                    already=intent.feature_plan if intent else [],

                )

                if intent and intent.primary

                else [],

                "bots": self.list_bots(user_id, limit=3),

            }

    def merge_session_answers_into_known(

            self, user_id: int, known: dict[str, Any], *, session_id: str = "default"

        ) -> dict[str, Any]:

            iron = self.recall_known(user_id, session_id=session_id)

            merged = dict(iron)

            # caller known (from L1 text) wins over durable defaults when present

            for k, v in (known or {}).items():

                if v not in (None, "", [], False):

                    merged[k] = v

                elif k not in merged:

                    merged[k] = v

            # but empty L1 should not wipe durable

            for k, v in iron.items():

                if k not in known or known.get(k) in (None, "", [], False):

                    merged[k] = v

            return merged
