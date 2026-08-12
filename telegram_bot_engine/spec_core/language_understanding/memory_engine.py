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


from .memory_store import MemoryStoreMixin
from .memory_retrieval import MemoryRetrievalMixin
from .memory_session import MemorySessionMixin


class MemoryEngine(MemoryStoreMixin, MemoryRetrievalMixin, MemorySessionMixin):
    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else _default_db_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init()



    # ── events ───────────────────────────────────────────────────

    # ── User memory ──────────────────────────────────────────────






    # ── Bots built registry ──────────────────────────────────────
    # ── Stage-2: persist extracted bot briefs (strict user intent) ──









    # ── Session memory ───────────────────────────────────────────







    # ── Pattern memory ───────────────────────────────────────────





    # ── Integration ──────────────────────────────────────────────






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
