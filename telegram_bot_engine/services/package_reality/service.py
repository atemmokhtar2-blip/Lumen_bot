"""
Package Reality Engine (v1 — Telegram bot stack)

Fetches live truth from PyPI (official JSON API) and compares with:
  - requirements*.txt declared versions
  - imports discovered via RepoContract / AST gaps

Goals for v1 product:
  - Know if a library is outdated vs latest
  - Detect yanked / missing-on-PyPI packages
  - Flag major-version lag (breaking risk)
  - Feed RepoIntelligence + chat without LLM

Cache: .tbe_package_reality_cache.json under project or /tmp (TTL hours)
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# Core stack we care about most in v1 (Telegram bots)
_CORE_BOT_PACKAGES = {
    "python-telegram-bot",
    "aiogram",
    "pytelegrambotapi",
    "pyrogram",
    "telethon",
    "python-dotenv",
    "pydantic",
    "pydantic-settings",
    "httpx",
    "aiohttp",
    "requests",
    "google-generativeai",
    "openai",
    "redis",
    "sqlalchemy",
    "asyncpg",
    "uvicorn",
    "fastapi",
}

_CACHE_TTL_SEC = 6 * 3600  # 6 hours
_PYPI = "https://pypi.org/pypi/{name}/json"
_UA = "ai-Agent-7h-bot-PackageReality/1.0 (+local; v1 bot quality)"


@dataclass
class PackageStatus:
    name: str
    declared: str = ""          # from requirements
    latest: str = ""            # from PyPI
    on_pypi: bool = False
    yanked: bool = False
    requires_python: str = ""
    summary: str = ""
    status: str = "unknown"     # ok | outdated | major_lag | missing | yanked | not_on_pypi | error
    severity: str = "info"      # info | low | medium | high
    message_ar: str = ""
    source: str = "pypi"
    checked_at: float = 0.0


@dataclass
class PackageHealthReport:
    packages: list[PackageStatus] = field(default_factory=list)
    outdated_count: int = 0
    major_lag_count: int = 0
    missing_count: int = 0
    yanked_count: int = 0
    health_score: float = 1.0  # 0..1
    checked_at: float = 0.0
    notes: list[str] = field(default_factory=list)

    def to_user_text(self) -> str:
        lines = [
            "📦 *صحة الحزم (Package Reality — حي من PyPI)*",
            f"• الدرجة: {self.health_score:.0%}",
            f"• outdated: {self.outdated_count} | major_lag: {self.major_lag_count} | "
            f"missing: {self.missing_count} | yanked: {self.yanked_count}",
        ]
        # show important ones first
        order = {"yanked": 0, "not_on_pypi": 1, "missing": 2, "major_lag": 3, "outdated": 4, "ok": 5, "error": 6, "unknown": 7}
        ordered = sorted(self.packages, key=lambda p: (order.get(p.status, 9), p.name))
        for p in ordered[:18]:
            ver = p.declared or "—"
            latest = p.latest or "—"
            lines.append(
                f"• `{p.name}` {ver} → latest `{latest}` | *{p.status}*"
                + (f" — {p.message_ar}" if p.message_ar else "")
            )
        if self.notes:
            lines.append("• " + " | ".join(self.notes[:4]))
        return "\n".join(lines)


def _norm_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", (name or "").strip().lower())


def _parse_req_line(line: str) -> tuple[str, str] | None:
    line = (line or "").strip()
    if not line or line.startswith("#") or line.startswith("-"):
        return None
    # strip env markers
    line = line.split(";", 1)[0].strip()
    m = re.match(
        r"^([A-Za-z0-9][A-Za-z0-9._\-]*)\s*((?:[=<>!~]=?|===)\s*[^,\s]+(?:,\s*(?:[=<>!~]=?|===)\s*[^,\s]+)*)?",
        line,
    )
    if not m:
        return None
    name = m.group(1)
    ver = (m.group(2) or "").strip()
    return name, ver


def _read_requirements(root: Path) -> dict[str, str]:
    found: dict[str, str] = {}
    for fname in ("requirements.txt", "requirements-bot.txt", "reqs.txt"):
        p = root / fname
        if not p.is_file():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in text.splitlines():
            parsed = _parse_req_line(line)
            if not parsed:
                continue
            name, ver = parsed
            key = _norm_name(name)
            # keep first declaration
            if key not in found:
                found[key] = ver
    return found


def _version_tuple(v: str) -> tuple:
    """Best-effort numeric version tuple for comparison."""
    v = (v or "").strip()
    v = re.sub(r"^[=<>!~]+\s*", "", v)
    v = v.split(",")[0].strip()
    v = re.sub(r"^[=<>!~]+", "", v).strip()
    parts = re.findall(r"\d+", v)
    if not parts:
        return (0,)
    return tuple(int(x) for x in parts[:4])


def _declared_lower_bound(spec: str) -> str:
    """Extract a concrete version-ish from requirement specifier."""
    if not spec:
        return ""
    # prefer == then >= then bare
    m = re.search(r"==\s*([0-9][0-9a-zA-Z.\-]*)", spec)
    if m:
        return m.group(1)
    m = re.search(r">=\s*([0-9][0-9a-zA-Z.\-]*)", spec)
    if m:
        return m.group(1)
    m = re.search(r"~=\s*([0-9][0-9a-zA-Z.\-]*)", spec)
    if m:
        return m.group(1)
    m = re.search(r"([0-9]+\.[0-9a-zA-Z.\-]*)", spec)
    return m.group(1) if m else ""


def _major(v: str) -> int:
    t = _version_tuple(v)
    return int(t[0]) if t else 0


class PackageRealityEngine:
    def __init__(self, cache_path: Path | None = None, ttl_sec: int = _CACHE_TTL_SEC) -> None:
        self.cache_path = cache_path or Path("/tmp/tbe_package_reality_cache.json")
        self.ttl_sec = ttl_sec
        self._cache: dict[str, Any] = self._load_cache()

    def _load_cache(self) -> dict[str, Any]:
        try:
            if self.cache_path.is_file():
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except Exception:
            pass
        return {}

    def _save_cache(self) -> None:
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(
                json.dumps(self._cache, ensure_ascii=False, indent=0),
                encoding="utf-8",
            )
        except Exception:
            pass

    def fetch_pypi(self, name: str) -> dict[str, Any] | None:
        key = _norm_name(name)
        now = time.time()
        hit = self._cache.get(key)
        if hit and now - float(hit.get("fetched_at", 0)) < self.ttl_sec:
            return hit.get("data")

        url = _PYPI.format(name=key)
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                self._cache[key] = {"fetched_at": now, "data": None, "not_found": True}
                self._save_cache()
                return None
            return {"_error": f"http_{e.code}"}
        except Exception as e:
            return {"_error": f"{type(e).__name__}"}

        self._cache[key] = {"fetched_at": now, "data": data}
        self._save_cache()
        return data

    def assess_package(self, name: str, declared_spec: str = "") -> PackageStatus:
        now = time.time()
        data = self.fetch_pypi(name)
        if data is None:
            return PackageStatus(
                name=name,
                declared=declared_spec,
                on_pypi=False,
                status="not_on_pypi",
                severity="high",
                message_ar="غير موجودة على PyPI",
                checked_at=now,
            )
        if isinstance(data, dict) and data.get("_error"):
            return PackageStatus(
                name=name,
                declared=declared_spec,
                status="error",
                severity="medium",
                message_ar=f"تعذر الجلب: {data['_error']}",
                checked_at=now,
            )

        info = data.get("info") or {}
        latest = str(info.get("version") or "")
        yanked = bool(info.get("yanked"))
        requires_python = str(info.get("requires_python") or "")
        summary = str(info.get("summary") or "")[:160]
        declared_ver = _declared_lower_bound(declared_spec)

        status = "ok"
        severity = "info"
        msg = ""

        if yanked:
            status = "yanked"
            severity = "high"
            msg = "الإصدار المسحوب/yanked على PyPI"
        elif not declared_spec:
            status = "ok"
            msg = f"أحدث على PyPI: {latest}"
        elif declared_ver and latest:
            if _version_tuple(declared_ver) < _version_tuple(latest):
                if _major(declared_ver) < _major(latest):
                    status = "major_lag"
                    severity = "high"
                    msg = f"تأخر major: {declared_ver} ← {latest} (خطر كسر توافق)"
                else:
                    status = "outdated"
                    severity = "medium"
                    msg = f"يتوفر أحدث: {latest}"
            else:
                status = "ok"
                msg = "متوافق مع أحدث معروف"
        else:
            status = "ok"
            msg = f"latest={latest}" if latest else ""

        return PackageStatus(
            name=info.get("name") or name,
            declared=declared_spec or declared_ver,
            latest=latest,
            on_pypi=True,
            yanked=yanked,
            requires_python=requires_python,
            summary=summary,
            status=status,
            severity=severity,
            message_ar=msg,
            checked_at=now,
        )

    def assess_repo(
        self,
        root: str | Path,
        extra_packages: list[str] | None = None,
        always_core: bool = True,
    ) -> PackageHealthReport:
        root = Path(root)
        declared = _read_requirements(root)
        names: set[str] = set(declared.keys())
        if always_core:
            # only include core if present in reqs OR explicitly extra — avoid noise
            for c in _CORE_BOT_PACKAGES:
                if _norm_name(c) in declared:
                    names.add(_norm_name(c))
        if extra_packages:
            for p in extra_packages:
                if p:
                    names.add(_norm_name(p))

        packages: list[PackageStatus] = []
        for name in sorted(names):
            packages.append(self.assess_package(name, declared.get(name, "")))

        outdated = sum(1 for p in packages if p.status == "outdated")
        major_lag = sum(1 for p in packages if p.status == "major_lag")
        missing = sum(1 for p in packages if p.status in ("missing", "not_on_pypi"))
        yanked = sum(1 for p in packages if p.status == "yanked")

        # health score
        score = 1.0
        score -= 0.08 * outdated
        score -= 0.18 * major_lag
        score -= 0.25 * yanked
        score -= 0.20 * missing
        score = max(0.0, min(1.0, round(score, 3)))

        notes = ["مصدر: PyPI JSON API", f"TTL كاش: {self.ttl_sec // 3600}س"]
        if not packages:
            notes.append("لا تبعيات في requirements للفحص")

        return PackageHealthReport(
            packages=packages,
            outdated_count=outdated,
            major_lag_count=major_lag,
            missing_count=missing,
            yanked_count=yanked,
            health_score=score,
            checked_at=time.time(),
            notes=notes,
        )


def assess_repo_packages(
    root: str | Path,
    extra_packages: list[str] | None = None,
) -> PackageHealthReport:
    return PackageRealityEngine().assess_repo(root, extra_packages=extra_packages)


@dataclass
class UpgradeRecommendation:
    name: str
    from_spec: str
    to_spec: str
    kind: str  # safe_minor | major_manual | yanked_fix
    reason_ar: str
    auto_applicable: bool = False


def recommend_upgrades(report: PackageHealthReport) -> list[UpgradeRecommendation]:
    """Build upgrade recommendations from a health report."""
    recs: list[UpgradeRecommendation] = []
    for p in report.packages:
        if not p.latest:
            continue
        if p.status == "yanked":
            recs.append(
                UpgradeRecommendation(
                    name=p.name,
                    from_spec=p.declared or "",
                    to_spec=f"{p.name}>={p.latest}",
                    kind="yanked_fix",
                    reason_ar=f"الإصدار مسحوب — ثبّت latest {p.latest}",
                    auto_applicable=True,
                )
            )
        elif p.status == "outdated":
            recs.append(
                UpgradeRecommendation(
                    name=p.name,
                    from_spec=p.declared or "",
                    to_spec=f"{p.name}>={p.latest}",
                    kind="safe_minor",
                    reason_ar=p.message_ar or f"ترقية آمنة إلى {p.latest}",
                    auto_applicable=True,
                )
            )
        elif p.status == "major_lag":
            recs.append(
                UpgradeRecommendation(
                    name=p.name,
                    from_spec=p.declared or "",
                    to_spec=f"{p.name}>={p.latest}",
                    kind="major_manual",
                    reason_ar=p.message_ar
                    or f"ترقية major إلى {p.latest} — راجع التغييرات أولاً",
                    auto_applicable=False,
                )
            )
    return recs


def apply_safe_upgrades(
    root: str | Path, *, include_major: bool = False
) -> tuple[list[str], str]:
    """
    Rewrite requirements for auto-applicable upgrades only.
    Returns (changed_package_names, message_ar).
    """
    root = Path(root)
    engine = PackageRealityEngine()
    report = engine.assess_repo(root)
    recs = recommend_upgrades(report)
    applicable = [
        r
        for r in recs
        if r.auto_applicable or (include_major and r.kind == "major_manual")
    ]
    if not applicable:
        manual = [r for r in recs if not r.auto_applicable]
        msg = "لا ترقيات آمنة للتطبيق تلقائياً."
        if manual:
            msg += " يحتاج مراجعة يدوية: " + ", ".join(
                f"`{r.name}` ({r.kind})" for r in manual[:8]
            )
        return [], msg

    req_path = None
    for fname in ("requirements.txt", "requirements-bot.txt", "reqs.txt"):
        p = root / fname
        if p.is_file():
            req_path = p
            break
    if req_path is None:
        req_path = root / "requirements.txt"
        req_path.write_text("", encoding="utf-8")

    text = req_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    changed: list[str] = []
    by_norm = {_norm_name(r.name): r for r in applicable}

    new_lines: list[str] = []
    seen: set[str] = set()
    for line in lines:
        parsed = _parse_req_line(line)
        if not parsed:
            new_lines.append(line)
            continue
        name, _ver = parsed
        key = _norm_name(name)
        if key in by_norm:
            rec = by_norm[key]
            new_lines.append(rec.to_spec)
            changed.append(rec.name)
            seen.add(key)
        else:
            new_lines.append(line)

    for key, rec in by_norm.items():
        if key not in seen:
            new_lines.append(rec.to_spec)
            changed.append(rec.name)

    if not changed:
        return [], "لم يتغير أي سطر في requirements."

    body = "\n".join(new_lines).rstrip() + "\n"
    if "# package-reality-safe-upgrade" not in body:
        body += "\n# package-reality-safe-upgrade applied\n"
    req_path.write_text(body, encoding="utf-8")
    return changed, (
        "تُطبّقت ترقيات آمنة على `"
        + req_path.name
        + "`: "
        + ", ".join("`" + c + "`" for c in changed)
    )


def format_recommendations(recs: list[UpgradeRecommendation]) -> str:
    if not recs:
        return "لا توصيات ترقية حالياً."
    lines = ["🔧 *توصيات الترقية (Package Reality)*"]
    for r in recs:
        flag = "⚡" if r.auto_applicable else "🖐"
        lines.append(
            f"• {flag} `{r.name}`: `{r.from_spec or '—'}` → `{r.to_spec}` "
            f"({r.kind}) — {r.reason_ar}"
        )
    lines.append(
        "نفّذ الآمن: «طبّق الترقيات الآمنة» | major يدوياً بعد المراجعة."
    )
    return "\n".join(lines)
