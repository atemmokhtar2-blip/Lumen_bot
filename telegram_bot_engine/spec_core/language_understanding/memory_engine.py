"""Layer 4 — Iron Memory Engine (SQLite, zero-AI).

Remembers hard across restarts and sessions:
  • User profile + durable slot preferences (payment, delivery, language…)
  • Full interaction ledger (not only last 5)
  • Built bots registry (name, intent, features, paths)
  • Session Q&A with promotion of answers → durable prefs
  • Global pattern stats for suggestions
  • Feedback / pain points

Goal: never re-ask what the user already taught the system.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .engine import LanguageUnderstandingResult
from .intent_analysis import IntentAnalysis


def _default_db_path() -> Path:
    # Prefer explicit MEMORY_DB_PATH, then durable data dir under OUTPUT_DIR, else cwd/data
    env = (os.getenv("MEMORY_DB_PATH") or "").strip()
    if env:
        path = Path(env)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    out = (os.getenv("OUTPUT_DIR") or "").strip()
    base = (Path(out) / "data") if out else (Path.cwd() / "data")
    base.mkdir(parents=True, exist_ok=True)
    return base / "memory_engine.sqlite3"


def _now() -> float:
    return time.time()


def _clip(s: str, n: int = 500) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# Slots worth promoting from session → durable user prefs
_DURABLE_SLOTS = {
    "payment",
    "delivery",
    "discounts",
    "language_ui",
    "product_or_category",
    "security_scope",
    "report_audience",
    "audience",
    "priority_sla",
    "booking_type",
    "course_scope",
    "connectivity",
    "ops_scope",
    "pipeline",
    "plans",
    "game_loop",
    "mod_actions",
    "menu_or_orders",
}


@dataclass
class UserProfile:
    user_id: int
    language_preference: str = "ar"
    skill_level: str = "beginner"
    bot_types_built: list[str] = field(default_factory=list)
    preferred_features: list[str] = field(default_factory=list)
    naming_style: str = "mixed"
    complexity_preference: str = "simple"
    last_interactions: list[dict[str, Any]] = field(default_factory=list)
    pain_points: list[str] = field(default_factory=list)
    total_builds: int = 0
    durable_slots: dict[str, Any] = field(default_factory=dict)  # permanent answers
    default_payments: list[str] = field(default_factory=list)
    default_wants_delivery: bool | None = None
    default_wants_discounts: bool | None = None
    favorite_intents: list[str] = field(default_factory=list)
    notes: str = ""
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
            last_interactions=list(d.get("last_interactions") or [])[:8],
            pain_points=list(d.get("pain_points") or []),
            total_builds=int(d.get("total_builds") or 0),
            durable_slots=dict(d.get("durable_slots") or {}),
            default_payments=list(d.get("default_payments") or []),
            default_wants_delivery=d.get("default_wants_delivery", None),
            default_wants_discounts=d.get("default_wants_discounts", None),
            favorite_intents=list(d.get("favorite_intents") or []),
            notes=str(d.get("notes") or ""),
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
    state: str = "idle"
    primary_intent: str | None = None
    feature_plan: list[str] = field(default_factory=list)
    started_at: float = 0.0
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
            started_at=float(d.get("started_at") or 0.0),
            updated_at=float(d.get("updated_at") or 0.0),
        )


@dataclass
class BuiltBotRecord:
    bot_id: str
    user_id: int
    name: str
    intent: str
    features: list[str]
    request_text: str
    preset: str | None = None
    output_path: str = ""
    success: bool = True
    created_at: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MemoryEngine:
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else _default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()

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

    # ── events ───────────────────────────────────────────────────
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

    # ── Bots built registry ──────────────────────────────────────
    # ── Stage-2: persist extracted bot briefs (strict user intent) ──
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

    # ── Session memory ───────────────────────────────────────────
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

    # ── Integration ──────────────────────────────────────────────
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
    "BuiltBotRecord",
    "MemoryEngine",
    "get_memory_engine",
]
