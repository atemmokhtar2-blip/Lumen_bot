"""Layer 4 — Memory Engine (SQLite, zero-AI).

Three stores:
  A) User Memory   — durable profile (skill, prefs, bot types built…)
  B) Session Memory — current build conversation (utterances, Q&A, state)
  C) Pattern Memory — global stats (co-occurrence probabilities)

All pure sqlite3. Thread-safe via lock + WAL.
"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .intent_analysis import IntentAnalysis
from .engine import LanguageUnderstandingResult


def _default_db_path() -> Path:
    root = Path(os.getenv("OUTPUT_DIR") or "/tmp/generated")
    root.mkdir(parents=True, exist_ok=True)
    return root / "memory_engine.sqlite3"


@dataclass
class UserProfile:
    user_id: int
    language_preference: str = "ar"
    skill_level: str = "beginner"  # beginner|intermediate|expert
    bot_types_built: list[str] = field(default_factory=list)
    preferred_features: list[str] = field(default_factory=list)
    naming_style: str = "mixed"  # ar|en|mixed
    complexity_preference: str = "simple"  # simple|medium|complex
    last_interactions: list[dict[str, Any]] = field(default_factory=list)  # max 5
    pain_points: list[str] = field(default_factory=list)
    total_builds: int = 0
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, user_id: int, data: dict[str, Any] | None) -> "UserProfile":
        d = data or {}
        return cls(
            user_id=int(user_id),
            language_preference=str(d.get("language_preference") or "ar"),
            skill_level=str(d.get("skill_level") or "beginner"),
            bot_types_built=list(d.get("bot_types_built") or []),
            preferred_features=list(d.get("preferred_features") or []),
            naming_style=str(d.get("naming_style") or "mixed"),
            complexity_preference=str(d.get("complexity_preference") or "simple"),
            last_interactions=list(d.get("last_interactions") or [])[:5],
            pain_points=list(d.get("pain_points") or []),
            total_builds=int(d.get("total_builds") or 0),
            updated_at=float(d.get("updated_at") or 0.0),
        )


@dataclass
class SessionMemory:
    user_id: int
    session_id: str
    utterances: list[str] = field(default_factory=list)
    understood: dict[str, Any] = field(default_factory=dict)
    questions_asked: list[dict[str, Any]] = field(default_factory=list)
    answers: dict[str, Any] = field(default_factory=dict)
    edits: list[dict[str, Any]] = field(default_factory=list)
    state: str = "idle"  # idle|clarifying|ready|generating|done
    primary_intent: str | None = None
    feature_plan: list[str] = field(default_factory=list)
    updated_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, user_id: int, session_id: str, data: dict[str, Any] | None) -> "SessionMemory":
        d = data or {}
        return cls(
            user_id=int(user_id),
            session_id=str(session_id),
            utterances=list(d.get("utterances") or []),
            understood=dict(d.get("understood") or {}),
            questions_asked=list(d.get("questions_asked") or []),
            answers=dict(d.get("answers") or {}),
            edits=list(d.get("edits") or []),
            state=str(d.get("state") or "idle"),
            primary_intent=d.get("primary_intent"),
            feature_plan=list(d.get("feature_plan") or []),
            updated_at=float(d.get("updated_at") or 0.0),
        )


class MemoryEngine:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else _default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(str(self.path), timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        try:
            c.execute("PRAGMA journal_mode=WAL")
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
                    CREATE TABLE IF NOT EXISTS pattern_skill (
                        skill TEXT NOT NULL,
                        phrase TEXT NOT NULL,
                        count INTEGER NOT NULL DEFAULT 0,
                        PRIMARY KEY (skill, phrase)
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
                    """
                )
                conn.commit()

    # ── User memory ──────────────────────────────────────────────
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
        profile.updated_at = time.time()
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
            # skill: ratchet up, never hard-drop from one message
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
                profile.complexity_preference = intent.complexity
            if intent.primary:
                bt = intent.primary.intent
                if bt not in profile.bot_types_built:
                    # only record after successful build; for now track seen types lightly
                    pass
                profile.bot_types_built = list(
                    dict.fromkeys(profile.bot_types_built + ([bt] if success else []))
                )[:20]
            if features_accepted:
                merged = list(dict.fromkeys(profile.preferred_features + list(features_accepted)))
                profile.preferred_features = merged[:40]
            elif intent.feature_plan:
                # soft preference from plans user accepted by not rejecting
                soft = [f for f in intent.feature_plan if f not in profile.preferred_features]
                profile.preferred_features = (profile.preferred_features + soft[:5])[:40]

        # naming style heuristic
        if text:
            import re
            ar = len(re.findall(r"[\u0600-\u06FF]", text))
            en = len(re.findall(r"[A-Za-z]", text))
            if ar and en:
                profile.naming_style = "mixed"
            elif ar:
                profile.naming_style = "ar"
            elif en:
                profile.naming_style = "en"

        interaction = {
            "text": (text or "")[:300],
            "intent": intent.primary.intent if intent and intent.primary else None,
            "ts": time.time(),
            "success": success,
        }
        profile.last_interactions = (profile.last_interactions + [interaction])[-5:]
        if success:
            profile.total_builds += 1
        self.save_user(profile)
        return profile

    def add_pain_point(self, user_id: int, note: str) -> None:
        profile = self.get_user(user_id)
        note = (note or "").strip()[:200]
        if note and note not in profile.pain_points:
            profile.pain_points = (profile.pain_points + [note])[-15:]
            self.save_user(profile)

    # ── Session memory ───────────────────────────────────────────
    def get_session(self, user_id: int, session_id: str = "default") -> SessionMemory:
        with self._lock:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT data_json FROM session_memory WHERE user_id=? AND session_id=?",
                    (int(user_id), str(session_id)),
                ).fetchone()
        if not row:
            return SessionMemory(user_id=int(user_id), session_id=str(session_id))
        try:
            data = json.loads(row["data_json"] or "{}")
        except Exception:
            data = {}
        return SessionMemory.from_dict(int(user_id), str(session_id), data if isinstance(data, dict) else {})

    def save_session(self, session: SessionMemory) -> None:
        session.updated_at = time.time()
        # bound growth
        session.utterances = session.utterances[-30:]
        session.questions_asked = session.questions_asked[-40:]
        session.edits = session.edits[-30:]
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
            sess.utterances.append(text[:1000])
        if intent:
            sess.primary_intent = intent.primary.intent if intent.primary else sess.primary_intent
            sess.feature_plan = list(intent.feature_plan or sess.feature_plan)
            sess.understood = {
                **sess.understood,
                "intent": intent.to_dict() if hasattr(intent, "to_dict") else {},
                **(understood or {}),
            }
            if intent.should_ask:
                sess.state = "clarifying"
            else:
                sess.state = "ready"
        elif understood:
            sess.understood = {**sess.understood, **understood}
        self.save_session(sess)
        return sess

    def record_questions(self, user_id: int, questions: list[dict[str, Any]], *, session_id: str = "default") -> SessionMemory:
        sess = self.get_session(user_id, session_id)
        for q in questions:
            sess.questions_asked.append({"q": q, "ts": time.time()})
        if questions:
            sess.state = "clarifying"
        self.save_session(sess)
        return sess

    def record_answer(self, user_id: int, slot: str, answer: str, *, session_id: str = "default") -> SessionMemory:
        sess = self.get_session(user_id, session_id)
        sess.answers[str(slot)] = answer
        sess.edits.append({"slot": slot, "answer": answer, "ts": time.time()})
        self.save_session(sess)
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

    # ── Pattern memory ───────────────────────────────────────────
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
                for f in feats[:30]:
                    conn.execute(
                        """
                        INSERT INTO pattern_cooccur(intent, feature, count) VALUES(?,?,1)
                        ON CONFLICT(intent, feature) DO UPDATE SET count=count+1
                        """,
                        (intent, f),
                    )
                if skill and text:
                    # store short skill phrase markers
                    marker = "simple" if "بسيط" in (text or "") or "simple" in (text or "").lower() else ""
                    if marker:
                        conn.execute(
                            """
                            INSERT INTO pattern_skill(skill, phrase, count) VALUES(?,?,1)
                            ON CONFLICT(skill, phrase) DO UPDATE SET count=count+1
                            """,
                            (skill, marker),
                        )
                conn.commit()

    def top_features_for_intent(self, intent: str, *, limit: int = 8) -> list[tuple[str, float]]:
        """Return (feature, probability) sorted by co-occurrence rate."""
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

    def suggest_features(self, intent: str, *, already: list[str] | None = None, min_p: float = 0.35) -> list[dict[str, Any]]:
        already_set = set(already or [])
        out = []
        for feat, p in self.top_features_for_intent(intent, limit=12):
            if feat in already_set:
                continue
            if p < min_p:
                continue
            out.append({"feature": feat, "probability": p})
        return out

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
                        (liked or "")[:300],
                        (disliked or "")[:300],
                        time.time(),
                    ),
                )
                conn.commit()
        if disliked:
            self.add_pain_point(user_id, disliked[:200])

    # ── Integration helpers ──────────────────────────────────────
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
        """One-call update: user + session + patterns."""
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
            "suggestions": self.suggest_features(
                intent.primary.intent,
                already=intent.feature_plan if intent else [],
            )
            if intent and intent.primary
            else [],
        }

    def merge_session_answers_into_known(self, user_id: int, known: dict[str, Any], *, session_id: str = "default") -> dict[str, Any]:
        """Layer-3 helper: session answers count as known slots."""
        sess = self.get_session(user_id, session_id)
        merged = dict(known)
        for slot, ans in (sess.answers or {}).items():
            if ans not in (None, ""):
                merged[slot] = ans
        return merged

    def prefer_user_defaults(self, user_id: int, feature_plan: list[str]) -> list[str]:
        """Prepend user's historically preferred features when relevant."""
        profile = self.get_user(user_id)
        out = list(feature_plan)
        for f in profile.preferred_features:
            if f not in out:
                out.append(f)
        return out[:50]


_ENGINE: MemoryEngine | None = None
_ENGINE_LOCK = threading.Lock()


def get_memory_engine(path: str | Path | None = None) -> MemoryEngine:
    global _ENGINE
    with _ENGINE_LOCK:
        if _ENGINE is None or (path and Path(path) != _ENGINE.path):
            _ENGINE = MemoryEngine(path=path)
        return _ENGINE


__all__ = [
    "UserProfile",
    "SessionMemory",
    "MemoryEngine",
    "get_memory_engine",
]
