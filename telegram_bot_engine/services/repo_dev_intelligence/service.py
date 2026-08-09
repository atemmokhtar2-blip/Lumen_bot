"""
Repo Development Intelligence — phase 2 after full repo understanding.

Uses RepoContract + CodeGraph + RepoIntelligence to:
  - build a deterministic development plan from a natural request
  - suggest exact edit targets (files/functions)
  - apply safe dependency gap fills into requirements.txt

No LLM. Rules + graph only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ...schemas.repo_contract import RepoContract


@dataclass
class DevStep:
    id: str
    title_ar: str
    kind: str  # analyze | edit | deps | test | host | manual
    target: str = ""
    detail: str = ""
    auto: bool = False  # can be applied without LLM


@dataclass
class DevPlan:
    goal: str
    steps: list[DevStep] = field(default_factory=list)
    targets: list[str] = field(default_factory=list)
    readiness: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_user_text(self) -> str:
        lines = [
            "🛠 *خطة تطوير المستودع (ذكاء حتمي)*",
            f"• الهدف: {self.goal or '—'}",
            f"• جاهزية التطوير: {self.readiness:.0%}",
        ]
        if self.targets:
            lines.append("• أهداف التعديل: " + ", ".join(f"`{t}`" for t in self.targets[:8]))
        if self.steps:
            lines.append("• الخطوات:")
            for i, s in enumerate(self.steps, 1):
                flag = "⚡" if s.auto else "🖐"
                lines.append(f"  {i}. {flag} *{s.title_ar}*")
                if s.target:
                    lines.append(f"     → `{s.target}`")
                if s.detail:
                    lines.append(f"     {s.detail}")
        if self.notes:
            lines.append("• ملاحظات: " + " | ".join(self.notes[:5]))
        lines.append(
            "\nأوامر سريعة: `أضف أمر /x` · `سد فجوات التبعيات` · `أين أعدّل` · `خطة تطوير` · `استضف`"
        )
        return "\n".join(lines)


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def suggest_edit_targets(contract: RepoContract, limit: int = 10) -> list[str]:
    """Best files/functions to touch for iterative development."""
    targets: list[str] = []
    intel = contract.intelligence
    if intel and intel.change_surface:
        for t in intel.change_surface:
            if t not in targets:
                targets.append(t)
    for ep in contract.entry_points or []:
        if ep.path and ep.path not in targets:
            targets.append(ep.path)
    g = contract.code_graph
    if g and g.functions:
        # Prefer handler/main functions with many calls (central logic)
        ranked = sorted(
            g.functions,
            key=lambda f: (
                0 if any(x in f.file.lower() for x in ("handler", "main", "bot")) else 1,
                -len(f.calls),
            ),
        )
        for f in ranked[:15]:
            label = f"{f.file}::{f.qualname}"
            if label not in targets:
                targets.append(label)
            if len(targets) >= limit:
                break
    for name in ("handlers.py", "main.py", "bot.py", "keyboards.py", "config.py"):
        if name not in targets:
            targets.append(name)
    return targets[:limit]


def apply_dependency_gaps(root: Path, contract: RepoContract) -> tuple[list[str], str]:
    """
    Append intelligence.dependency_gaps packages to requirements.txt.
    Returns (added_packages, message).
    """
    intel = contract.intelligence
    if not intel or not intel.dependency_gaps:
        return [], "لا توجد فجوات تبعيات مكتشفة."

    req = root / "requirements.txt"
    existing = ""
    if req.exists():
        existing = req.read_text(encoding="utf-8", errors="ignore")
    present = {
        re.split(r"[<>=!~;\[]", ln)[0].strip().lower().replace("_", "-")
        for ln in existing.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    }

    added: list[str] = []
    lines: list[str] = []
    for gap in intel.dependency_gaps:
        pkg = (gap.suggested_package or "").strip()
        if not pkg:
            continue
        key = pkg.lower().replace("_", "-")
        if key in present:
            continue
        lines.append(pkg)
        added.append(pkg)
        present.add(key)

    if not added:
        return [], "كل الفجوات مغطاة بالفعل في requirements."

    if existing and not existing.endswith("\n"):
        existing += "\n"
    if "# repo-dev-intelligence" not in existing:
        existing += "\n# repo-dev-intelligence\n"
    existing += "\n".join(lines) + "\n"
    req.write_text(existing, encoding="utf-8")
    return added, f"تمت إضافة {len(added)} حزمة إلى requirements.txt: " + ", ".join(f"`{p}`" for p in added)


def build_dev_plan(contract: RepoContract, request: str = "") -> DevPlan:
    """Build a concrete development plan from contract + optional user goal text."""
    t = _norm(request)
    goal = (request or "").strip() or "تطوير عام للمستودع النشط"
    steps: list[DevStep] = []
    notes: list[str] = []
    targets = suggest_edit_targets(contract)
    readiness = 0.4
    if contract.intelligence:
        readiness = max(readiness, contract.intelligence.host_readiness * 0.85)
    if contract.code_graph and contract.code_graph.function_count > 0:
        readiness = min(0.99, readiness + 0.1)
    if contract.is_telegram_bot:
        readiness = min(0.99, readiness + 0.05)

    # Always start from understanding status
    steps.append(DevStep(
        id="context",
        title_ar="الاعتماد على الفهم الحالي (RepoContract + CodeGraph)",
        kind="analyze",
        detail=(
            f"أوامر={len(contract.commands)} | "
            f"دوال={contract.code_graph.function_count if contract.code_graph else 0} | "
            f"إطار={', '.join(contract.frameworks[:3]) or '—'}"
        ),
        auto=True,
    ))

    intel = contract.intelligence
    if intel and intel.dependency_gaps:
        pkgs = ", ".join(g.suggested_package for g in intel.dependency_gaps[:6] if g.suggested_package)
        steps.append(DevStep(
            id="deps",
            title_ar="سد فجوات التبعيات",
            kind="deps",
            target="requirements.txt",
            detail=f"حزم ناقصة: {pkgs}. نفّذ: «سد فجوات التبعيات»",
            auto=True,
        ))

    if intel and intel.env_gaps:
        steps.append(DevStep(
            id="env",
            title_ar="توثيق متغيرات البيئة الحساسة",
            kind="manual",
            target=".env.example",
            detail="ناقص: " + ", ".join(intel.env_gaps[:6]),
            auto=False,
        ))

    # Goal-specific steps from keywords
    wants_command = any(k in t for k in ("أمر", "امر", "command", "stats", "help", "start"))
    wants_ai = any(k in t for k in ("ai", "ذكي", "gemini", "openai", "gpt", "ذكاء"))
    wants_fix = any(k in t for k in ("صلح", "أصلح", "fix", "bug", "خطأ", "error"))
    wants_feature = any(k in t for k in ("ضيف", "أضف", "اضف", "feature", "ميزة", "طور", "طوّر", "improve"))
    wants_host = any(k in t for k in ("استضف", "host", "نشر", "شغل", "تشغيل"))

    if wants_command or (wants_feature and contract.is_telegram_bot):
        entry = targets[0] if targets else "main.py"
        steps.append(DevStep(
            id="add_cmd",
            title_ar="إضافة/تعديل أوامر على سطح التسجيل",
            kind="edit",
            target=entry,
            detail="مثال: «أضف أمر /stats» — التسجيل يتم في نقطة الدخول المكتشفة",
            auto=True,
        ))

    if wants_ai:
        steps.append(DevStep(
            id="ai_integration",
            title_ar="دمج طبقة ذكاء (API خارجي)",
            kind="manual",
            detail="يحتاج مفتاح API + وحدة خدمة. حدّد المزود (Gemini/OpenAI) ثم أضف أمر يستدعيه",
            auto=False,
        ))
        notes.append("تكامل AI شبه آلي؛ المفتاح والإعداد يدوي")

    if wants_fix:
        steps.append(DevStep(
            id="fix_flow",
            title_ar="إصلاح عبر التشغيل الحي + Error Intelligence",
            kind="test",
            detail="شغّل حياً أو «استضف» ثم «تشخيص الاستضافة» لمعالجة ModuleNotFound/Syntax",
            auto=True,
        ))

    # Code-graph guided central modules
    if contract.code_graph and contract.code_graph.module_function_counts:
        top_mods = list(contract.code_graph.module_function_counts.keys())[:5]
        steps.append(DevStep(
            id="hotspots",
            title_ar="الوحدات الأكثر كثافة (مناطق التطوير)",
            kind="analyze",
            detail=" · ".join(f"`{m}`" for m in top_mods),
            auto=True,
        ))

    if wants_host or (intel and intel.host_ready):
        steps.append(DevStep(
            id="host",
            title_ar="استضافة بعد التطوير",
            kind="host",
            detail="اكتب «استضف» ثم أرسل توكن البوت",
            auto=True,
        ))
    elif contract.is_telegram_bot:
        steps.append(DevStep(
            id="host_later",
            title_ar="تحسين الجاهزية قبل الاستضافة",
            kind="host",
            detail="أكمل التبعيات ونقطة الدخول ثم استضف",
            auto=False,
        ))

    if not any(s.id in ("add_cmd", "ai_integration", "fix_flow") for s in steps):
        steps.append(DevStep(
            id="iterative",
            title_ar="تطوير تكراري آمن",
            kind="edit",
            target=targets[0] if targets else "",
            detail="استخدم: أضف أمر /x · احذف أمر /y · اعرض ملف · ابحث عن",
            auto=True,
        ))

    steps.append(DevStep(
        id="verify",
        title_ar="إعادة المسح بعد كل تعديل",
        kind="analyze",
        detail="«أعد المسح» لتحديث RepoContract + CodeGraph",
        auto=True,
    ))

    return DevPlan(
        goal=goal[:200],
        steps=steps,
        targets=targets,
        readiness=round(readiness, 3),
        notes=notes,
    )
