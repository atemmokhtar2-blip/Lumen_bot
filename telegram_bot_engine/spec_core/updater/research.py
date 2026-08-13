"""Web research for keeping zero-AI bot packs current.

Sources (no Google API key required):
  - PyPI JSON API (package versions)
  - python-telegram-bot docs / GitHub releases (best-effort)
  - Telegram Bot API site (best-effort)

This module does NOT invent features from random blogs. It gathers
version facts + release notes signals so the coding engine can stay
aligned with the market.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field, asdict
from typing import Any

logger = logging.getLogger(__name__)

USER_AGENT = "ai_Agent_7h_bot-updater/1.0 (+https://github.com/atemmokhtar2-blip/ai_Agent_7h_bot)"
TIMEOUT = 25


def _get(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json,text/html,*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace") if e.fp else ""
        return int(e.code), body
    except Exception as e:
        logger.warning("fetch failed %s: %s", url, e)
        return 0, str(e)


@dataclass
class PackageIntel:
    name: str
    latest_version: str = ""
    requires_python: str = ""
    home_page: str = ""
    info_url: str = ""
    error: str = ""


@dataclass
class ResearchReport:
    ok: bool
    packages: list[PackageIntel] = field(default_factory=list)
    telegram_api_hints: list[str] = field(default_factory=list)
    ptb_hints: list[str] = field(default_factory=list)
    recommended_requirements: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "packages": [asdict(p) for p in self.packages],
            "telegram_api_hints": list(self.telegram_api_hints),
            "ptb_hints": list(self.ptb_hints),
            "recommended_requirements": list(self.recommended_requirements),
            "notes": list(self.notes),
            "errors": list(self.errors),
        }


def fetch_pypi_package(name: str) -> PackageIntel:
    url = f"https://pypi.org/pypi/{name}/json"
    status, body = _get(url)
    if status != 200:
        return PackageIntel(name=name, error=f"http_{status}:{body[:120]}")
    try:
        data = json.loads(body)
        info = data.get("info") or {}
        return PackageIntel(
            name=name,
            latest_version=str(info.get("version") or ""),
            requires_python=str(info.get("requires_python") or ""),
            home_page=str(info.get("home_page") or info.get("project_url") or ""),
            info_url=url,
        )
    except Exception as e:
        return PackageIntel(name=name, error=f"parse:{type(e).__name__}")


def fetch_telegram_bot_api_hints() -> list[str]:
    """Best-effort scrape of recent API version marker from core.telegram.org."""
    status, body = _get("https://core.telegram.org/bots/api")
    hints: list[str] = []
    if status != 200:
        return [f"fetch_failed:{status}"]
    # Recent change headers look like: <h4><a...">API 7.x</a>...</h4>
    versions = re.findall(r"Bot API\s+([0-9]+\.[0-9]+)", body)
    if versions:
        # preserve order unique
        seen = []
        for v in versions:
            if v not in seen:
                seen.append(v)
        hints.append("recent_bot_api_versions:" + ",".join(seen[:8]))
    if "chat_member" in body.lower():
        hints.append("docs_mention_chat_member")
    if "reaction" in body.lower():
        hints.append("docs_mention_reactions")
    return hints or ["no_version_markers_parsed"]


def fetch_ptb_release_hints() -> list[str]:
    """GitHub releases API for python-telegram-bot (public)."""
    status, body = _get(
        "https://api.github.com/repos/python-telegram-bot/python-telegram-bot/releases?per_page=5"
    )
    if status != 200:
        return [f"github_releases_failed:{status}"]
    try:
        rows = json.loads(body)
    except Exception:
        return ["github_releases_parse_failed"]
    hints = []
    for row in rows[:5]:
        if not isinstance(row, dict):
            continue
        tag = str(row.get("tag_name") or "")
        name = str(row.get("name") or "")
        hints.append(f"release:{tag}:{name}"[:120])
    return hints


def research_stack(
    packages: list[str] | None = None,
) -> ResearchReport:
    packages = packages or [
        "python-telegram-bot",
        "python-dotenv",
        "httpx",
        "aiohttp",
    ]
    report = ResearchReport(ok=True)
    for name in packages:
        intel = fetch_pypi_package(name)
        report.packages.append(intel)
        if intel.error:
            report.errors.append(f"{name}:{intel.error}")
            report.ok = False

    report.telegram_api_hints = fetch_telegram_bot_api_hints()
    report.ptb_hints = fetch_ptb_release_hints()

    ptb = next((p for p in report.packages if p.name == "python-telegram-bot"), None)
    dotenv = next((p for p in report.packages if p.name == "python-dotenv"), None)
    reqs: list[str] = []
    if ptb and ptb.latest_version:
        # Stay on v21+ line if latest is 21/22; pin lower bound to major.minor
        ver = ptb.latest_version
        major = ver.split(".")[0]
        if major.isdigit() and int(major) >= 21:
            reqs.append(f"python-telegram-bot>={ver},<23")
        else:
            reqs.append("python-telegram-bot>=21.0,<23")
        report.notes.append(f"ptb_latest={ver}")
    else:
        reqs.append("python-telegram-bot>=21.0,<23")
        report.notes.append("ptb_latest_unknown_using_safe_default")

    if dotenv and dotenv.latest_version:
        reqs.append(f"python-dotenv>={dotenv.latest_version}")
    else:
        reqs.append("python-dotenv>=1.0.0")

    report.recommended_requirements = reqs
    if report.errors and ptb and ptb.latest_version:
        # partial success still useful
        report.ok = True
    return report


__all__ = [
    "PackageIntel",
    "ResearchReport",
    "research_stack",
    "fetch_pypi_package",
]
