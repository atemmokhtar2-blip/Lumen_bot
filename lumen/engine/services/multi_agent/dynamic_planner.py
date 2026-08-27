"""Dynamic multi-layer planner — replaces Telegram-only template planning.

Layers (each pure + testable):
  1. IntentClassifier  — what kind of software is requested
  2. FeatureExtractor  — features/constraints from free text + preferred_keys
  3. WorkspaceProbe    — existing files change refine vs greenfield plan
  4. TaskGraphBuilder  — intent-specific TaskTree / ExecutionPlan
  5. PlanAssembler     — single entry used by LangGraph node_plan

No LLM required for baseline quality; optional LLM enrichment stays in architect.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .plan_contract import ExecutionPlan, PlanTask


# ---------------------------------------------------------------------------
# Layer 1 — Intent
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PlanIntent:
    kind: str  # telegram_bot | discord_bot | whatsapp_bot | web_api | library | refine | general_app
    platform: str = ""
    confidence: float = 0.5
    reasons: tuple[str, ...] = ()


_TELEGRAM = re.compile(r"\b(telegram|تيليجرام|تلجرام|تلغرام|pyrogram|aiogram|python-telegram-bot)\b", re.I)
_DISCORD = re.compile(r"\b(discord|ديسكورد|discord\.py)\b", re.I)
_WHATSAPP = re.compile(r"\b(whatsapp|واتساب|واتس)\b", re.I)
_WEB = re.compile(r"\b(fastapi|flask|django|api\b|rest\b|webhook|موقع|web\s*app|express)\b", re.I)
_LIB = re.compile(r"\b(library|package|sdk|مكتبة|باكدج)\b", re.I)
_REFINE = re.compile(r"\b(refine|fix|أصلح|عدل|حسّن|improve|refactor|patch)\b", re.I)


def classify_intent(goal: str, *, preferred_keys: Iterable[str] | None = None) -> PlanIntent:
    text = (goal or "").strip()
    keys = " ".join(str(k) for k in (preferred_keys or []))
    blob = f"{text} {keys}"
    reasons: list[str] = []

    if _REFINE.search(blob) and _REFINE.search(text):
        # refine only if explicitly refine-like and not pure "generate bot"
        if not re.search(r"\b(generate|ول[ّد]|انشئ|أنشئ|اعمل بوت)\b", text, re.I):
            return PlanIntent("refine", confidence=0.7, reasons=("refine_keywords",))

    if _TELEGRAM.search(blob) or "telegram" in keys.lower():
        reasons.append("telegram_keyword")
        return PlanIntent("telegram_bot", platform="telegram", confidence=0.9, reasons=tuple(reasons))
    if _DISCORD.search(blob):
        return PlanIntent("discord_bot", platform="discord", confidence=0.9, reasons=("discord_keyword",))
    if _WHATSAPP.search(blob):
        return PlanIntent("whatsapp_bot", platform="whatsapp", confidence=0.85, reasons=("whatsapp_keyword",))
    if _WEB.search(blob):
        return PlanIntent("web_api", platform="web", confidence=0.8, reasons=("web_keyword",))
    if _LIB.search(blob):
        return PlanIntent("library", confidence=0.75, reasons=("library_keyword",))

    # Ambiguous "bot" without platform → still telegram only if product signals present
    if re.search(r"\bبوت\b|\bbot\b", blob, re.I):
        if re.search(r"handler|/start|token|telegram|تيلي", blob, re.I):
            return PlanIntent("telegram_bot", platform="telegram", confidence=0.65, reasons=("bot_with_product_signals",))
        # Prefer general_app plan over forcing telegram-only template
        return PlanIntent("general_app", confidence=0.55, reasons=("bot_ambiguous_general",))

    return PlanIntent("general_app", confidence=0.5, reasons=("fallback_general",))


# ---------------------------------------------------------------------------
# Layer 2 — Features from text
# ---------------------------------------------------------------------------

_FEATURE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(admin|أدمن|ادمن)\b", re.I), "admin"),
    (re.compile(r"\b(moderat|حظر|بان|mute)\b", re.I), "moderation"),
    (re.compile(r"\b(payment|payments|دفع|stripe|paypal)\b", re.I), "payments"),
    (re.compile(r"\b(ai|gpt|ذكاء|llm)\b", re.I), "ai_chat"),
    (re.compile(r"\b(database|sqlite|mongo|postgres|قاعدة)\b", re.I), "database"),
    (re.compile(r"\b(schedule|cron|جدولة)\b", re.I), "scheduler"),
    (re.compile(r"\b(auth|login|تسجيل)\b", re.I), "auth"),
    (re.compile(r"\b(file|رفع|upload|مستند)\b", re.I), "files"),
    (re.compile(r"\b(inline|زر|keyboard|أزرار)\b", re.I), "keyboards"),
    (re.compile(r"\b(multi.?lang|ترجمة|i18n)\b", re.I), "i18n"),
]


def extract_features(goal: str, preferred_keys: Iterable[str] | None = None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for k in preferred_keys or []:
        s = str(k).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
    text = goal or ""
    for rx, name in _FEATURE_PATTERNS:
        if rx.search(text) and name not in seen:
            seen.add(name)
            out.append(name)
    return out[:40]


# ---------------------------------------------------------------------------
# Layer 3 — Workspace probe
# ---------------------------------------------------------------------------

@dataclass
class WorkspaceSnapshot:
    exists: bool = False
    py_files: list[str] = field(default_factory=list)
    has_main: bool = False
    has_requirements: bool = False
    is_refine: bool = False


def probe_workspace(work_dir: str | Path | None) -> WorkspaceSnapshot:
    if not work_dir:
        return WorkspaceSnapshot()
    root = Path(work_dir)
    if not root.is_dir():
        return WorkspaceSnapshot()
    pys = []
    for p in sorted(root.rglob("*.py"))[:40]:
        try:
            pys.append(p.relative_to(root).as_posix())
        except Exception:
            continue
    snap = WorkspaceSnapshot(
        exists=True,
        py_files=pys,
        has_main=(root / "main.py").is_file() or any(x.endswith("main.py") for x in pys),
        has_requirements=(root / "requirements.txt").is_file(),
    )
    snap.is_refine = snap.has_main and len(pys) >= 1
    return snap


# ---------------------------------------------------------------------------
# Layer 4 — Task graph per intent
# ---------------------------------------------------------------------------

def _tasks_telegram(feats: list[str], *, refine: bool) -> list[PlanTask]:
    if refine:
        return [
            PlanTask(
                id="inspect",
                title="Inspect existing bot structure and handlers",
                files=["main.py"],
                acceptance=["list handlers and entrypoint understood"],
                priority=1,
            ),
            PlanTask(
                id="patch",
                title="Apply requested changes without wiping project",
                files=["main.py"],
                acceptance=["edits applied", "project still imports"],
                priority=1,
                depends_on=["inspect"],
            ),
            PlanTask(
                id="verify",
                title="Verify syntax and imports after patch",
                files=["main.py"],
                acceptance=["compileall passes"],
                priority=1,
                depends_on=["patch"],
            ),
        ]
    tasks = [
        PlanTask(
            id="scaffold",
            title="Scaffold Telegram bot project",
            files=["main.py", "requirements.txt", "README.md", ".env.example"],
            acceptance=[
                "main.py valid Python",
                "python-telegram-bot or equivalent in requirements",
                "token from environment",
                "/start handler registered",
            ],
            priority=1,
        ),
    ]
    if feats:
        tasks.append(PlanTask(
            id="features",
            title="Implement features: " + ", ".join(feats[:12]),
            files=["main.py"] + [f"modules/{f}.py" for f in feats[:8]],
            acceptance=[f"feature working: {f}" for f in feats[:12]],
            priority=1,
            depends_on=["scaffold"],
        ))
        dep = ["features"]
    else:
        dep = ["scaffold"]
    tasks.append(PlanTask(
        id="harden",
        title="Error handling, logging, unknown-message fallback",
        files=["main.py"],
        acceptance=["safe fallback", "logging configured"],
        priority=2,
        depends_on=dep,
    ))
    tasks.append(PlanTask(
        id="verify",
        title="Compile and import self-check",
        files=["main.py"],
        acceptance=["compileall passes", "main importable"],
        priority=1,
        depends_on=["harden"],
    ))
    return tasks


def _tasks_discord(feats: list[str], *, refine: bool) -> list[PlanTask]:
    if refine:
        return _tasks_telegram(feats, refine=True)
    return [
        PlanTask(
            id="scaffold",
            title="Scaffold Discord bot (discord.py)",
            files=["main.py", "requirements.txt", "README.md", ".env.example"],
            acceptance=["discord.py in requirements", "bot client setup", "DISCORD_TOKEN from env"],
            priority=1,
        ),
        PlanTask(
            id="commands",
            title="Implement commands/events: " + (", ".join(feats[:10]) if feats else "ping, help"),
            files=["main.py"],
            acceptance=["at least one command responds"],
            priority=1,
            depends_on=["scaffold"],
        ),
        PlanTask(
            id="verify",
            title="Verify project compiles",
            files=["main.py"],
            acceptance=["compileall passes"],
            priority=1,
            depends_on=["commands"],
        ),
    ]


def _tasks_whatsapp(feats: list[str], *, refine: bool) -> list[PlanTask]:
    return [
        PlanTask(
            id="scaffold",
            title="Scaffold WhatsApp webhook bot",
            files=["main.py", "requirements.txt", "README.md", ".env.example"],
            acceptance=["webhook endpoint", "token/secrets from env"],
            priority=1,
        ),
        PlanTask(
            id="handlers",
            title="Message handlers: " + (", ".join(feats[:10]) if feats else "echo"),
            files=["main.py"],
            acceptance=["inbound message handled"],
            priority=1,
            depends_on=["scaffold"],
        ),
        PlanTask(
            id="verify",
            title="Verify project compiles",
            files=["main.py"],
            acceptance=["compileall passes"],
            priority=1,
            depends_on=["handlers"],
        ),
    ]


def _tasks_web_api(feats: list[str], *, refine: bool) -> list[PlanTask]:
    return [
        PlanTask(
            id="scaffold",
            title="Scaffold FastAPI/Flask application",
            files=["main.py", "requirements.txt", "README.md", ".env.example"],
            acceptance=["app entrypoint", "requirements list web framework"],
            priority=1,
        ),
        PlanTask(
            id="routes",
            title="Implement routes/features: " + (", ".join(feats[:10]) if feats else "health, root"),
            files=["main.py"],
            acceptance=["health or root route exists"],
            priority=1,
            depends_on=["scaffold"],
        ),
        PlanTask(
            id="verify",
            title="Verify project compiles and imports",
            files=["main.py"],
            acceptance=["compileall passes"],
            priority=1,
            depends_on=["routes"],
        ),
    ]


def _tasks_library(feats: list[str], *, refine: bool) -> list[PlanTask]:
    return [
        PlanTask(
            id="package",
            title="Create package layout and public API",
            files=["__init__.py", "pyproject.toml", "README.md"],
            acceptance=["importable package"],
            priority=1,
        ),
        PlanTask(
            id="implement",
            title="Implement core functions: " + (", ".join(feats[:10]) if feats else "public API"),
            files=[],
            acceptance=["core functions present"],
            priority=1,
            depends_on=["package"],
        ),
        PlanTask(
            id="tests",
            title="Add basic tests",
            files=["tests/test_basic.py"],
            acceptance=["at least one test file"],
            priority=2,
            depends_on=["implement"],
        ),
    ]


def _tasks_general(feats: list[str], *, refine: bool) -> list[PlanTask]:
    if refine:
        return _tasks_telegram(feats, refine=True)
    return [
        PlanTask(
            id="scaffold",
            title="Create project scaffold matching the request",
            files=["main.py", "requirements.txt", "README.md"],
            acceptance=["entrypoint exists", "README describes usage"],
            priority=1,
        ),
        PlanTask(
            id="implement",
            title="Implement requested behavior: " + (", ".join(feats[:12]) if feats else "core logic"),
            files=["main.py"],
            acceptance=["core behavior implemented"],
            priority=1,
            depends_on=["scaffold"],
        ),
        PlanTask(
            id="verify",
            title="Self-verify compile/imports",
            files=["main.py"],
            acceptance=["compileall passes"],
            priority=1,
            depends_on=["implement"],
        ),
    ]


_BUILDERS = {
    "telegram_bot": _tasks_telegram,
    "discord_bot": _tasks_discord,
    "whatsapp_bot": _tasks_whatsapp,
    "web_api": _tasks_web_api,
    "library": _tasks_library,
    "refine": lambda feats, refine: _tasks_telegram(feats, refine=True),
    "general_app": _tasks_general,
}


def build_task_list(intent: PlanIntent, feats: list[str], *, refine: bool) -> list[PlanTask]:
    fn = _BUILDERS.get(intent.kind, _tasks_general)
    return list(fn(feats, refine=refine or intent.kind == "refine"))


# ---------------------------------------------------------------------------
# Layer 5 — Assembler
# ---------------------------------------------------------------------------

def assemble_plan(
    *,
    goal: str,
    preferred_keys: Iterable[str] | None = None,
    constraints: Iterable[str] | None = None,
    language: str = "ar",
    work_dir: str | Path | None = None,
) -> ExecutionPlan:
    """Full dynamic plan used by node_plan / architect."""
    intent = classify_intent(goal, preferred_keys=preferred_keys)
    feats = extract_features(goal, preferred_keys)
    snap = probe_workspace(work_dir)
    refine = snap.is_refine or intent.kind == "refine"
    tasks = build_task_list(intent, feats, refine=refine)

    deliverables: list[str] = []
    for t in tasks:
        for f in t.files:
            if f not in deliverables:
                deliverables.append(f)
    if not deliverables:
        deliverables = ["main.py", "requirements.txt", "README.md"]

    constraints_l = list(constraints or [])[:20]
    constraints_l.append(f"intent:{intent.kind}")
    if intent.platform:
        constraints_l.append(f"platform:{intent.platform}")
    if refine:
        constraints_l.append("mode:incremental_repair")

    return ExecutionPlan(
        goal=(goal or "")[:2000],
        language=language or "ar",
        deliverables=deliverables[:30],
        tasks=tasks,
        constraints=constraints_l,
        features=feats[:40],
        version="dyn1",
    )


def plan_to_task_tree(plan: ExecutionPlan):
    from .task_tree import TaskTree
    return TaskTree.from_execution_plan(plan, goal=plan.goal)


__all__ = [
    "PlanIntent",
    "WorkspaceSnapshot",
    "classify_intent",
    "extract_features",
    "probe_workspace",
    "build_task_list",
    "assemble_plan",
    "plan_to_task_tree",
]
