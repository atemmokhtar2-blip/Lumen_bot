"""ResearchSpec — structured knowledge for future Dynamic Tool Builder (Phase 4).

Web research (later) fills these specs. Codegen stays deterministic and only
consumes approved CapabilityPack entries — never raw research text as code.
"""
from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from b2b_platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.capability_maestro'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ResearchSpec:
    feature_id: str
    title: str
    summary: str = ""
    libraries: list[str] = field(default_factory=list)
    apis: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    status: str = "draft"  # draft | approved | rejected
    source: str = "manual"  # manual | gap_journal | web (future)
    created_at: float = 0.0
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchSpec":
        return cls(
            feature_id=str(data.get("feature_id") or "").strip().lower(),
            title=str(data.get("title") or ""),
            summary=str(data.get("summary") or ""),
            libraries=[str(x) for x in (data.get("libraries") or [])],
            apis=[str(x) for x in (data.get("apis") or [])],
            patterns=[str(x) for x in (data.get("patterns") or [])],
            risks=[str(x) for x in (data.get("risks") or [])],
            dependencies=[str(x) for x in (data.get("dependencies") or [])],
            keywords=[str(x) for x in (data.get("keywords") or [])],
            status=str(data.get("status") or "draft"),
            source=str(data.get("source") or "manual"),
            created_at=float(data.get("created_at") or 0),
            meta=dict(data.get("meta") or {}),
        )


def _specs_dir() -> Path:
    base = os.getenv("OUTPUT_DIR") or _cm_default_output_dir()
    p = Path(base) / "platform" / "research_specs"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_research_spec(spec: ResearchSpec) -> Path:
    if not spec.created_at:
        spec.created_at = time.time()
    path = _specs_dir() / f"{spec.feature_id or 'spec'}.json"
    path.write_text(
        json.dumps(spec.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_research_spec(feature_id: str) -> ResearchSpec | None:
    path = _specs_dir() / f"{(feature_id or '').strip().lower()}.json"
    if not path.is_file():
        return None
    try:
        return ResearchSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None


def list_research_specs(*, status: str | None = None) -> list[ResearchSpec]:
    out: list[ResearchSpec] = []
    for path in sorted(_specs_dir().glob("*.json")):
        try:
            spec = ResearchSpec.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            continue
        if status and spec.status != status:
            continue
        out.append(spec)
    return out


def research_spec_from_gap(
    phrase: str,
    reason: str,
    *,
    request: str = "",
) -> ResearchSpec:
    """Create a draft ResearchSpec from a gap — no web call (safe foundation)."""
    fid = (
        "".join(ch if ch.isalnum() or ch in "_-" else "_" for ch in (phrase or "gap").lower())
        [:48]
        or "gap"
    )
    return ResearchSpec(
        feature_id=fid,
        title=phrase or "unknown gap",
        summary=reason or "",
        keywords=[w for w in (phrase or "").split() if len(w) > 2][:12],
        status="draft",
        source="gap_journal",
        created_at=time.time(),
        meta={"request_preview": (request or "")[:300], "reason": reason},
        risks=[
            "requires_review_before_pack_registration",
            "no_codegen_from_raw_research",
        ],
    )


__all__ = [
    "ResearchSpec",
    "save_research_spec",
    "load_research_spec",
    "list_research_specs",
    "research_spec_from_gap",
]
