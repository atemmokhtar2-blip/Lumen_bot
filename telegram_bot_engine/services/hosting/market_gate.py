"""Market-readiness gate for paid hosting.

Hosting is refused unless the deployment surface meets a minimum bar that
is safe to sell. Dev/local can set TBE_MARKET_GATE=0 to skip.

Required in production / when TBE_MARKET_GATE=1 (default outside pure dev):
  - ENVIRONMENT in {production, staging} OR TBE_MARKET_GATE=1
  - TBE_TOKEN_SECRET (>= 32 chars)
  - TBE_DOCKER_NETWORK set
  - Docker daemon available
  - TBE_SCALE_MODE=1 (queue workers — not sync docker on the API process)
  - TBE_DATABASE_URL postgres (control-plane state at commercial scale)
  - TBE_DOCKER_REGISTRY set (multi-node image pull)
  - TBE_DOCKER_PUSH=1
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _on(name: str, default: str = "0") -> bool:
    return (os.environ.get(name) or default).strip().lower() in {"1", "true", "yes", "on"}


def _env() -> str:
    return (os.environ.get("ENVIRONMENT") or os.getenv("TBE_ENV") or "").strip().lower()


@dataclass
class GateResult:
    ok: bool
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def message_ar(self) -> str:
        if self.ok:
            return "بوابة السوق: جاهز"
        lines = ["الاستضافة التجارية غير مفعّلة — ينقص:"]
        for m in self.missing:
            lines.append(f"• {m}")
        if self.warnings:
            lines.append("تحذيرات:")
            for w in self.warnings:
                lines.append(f"• {w}")
        lines.append("اضبط المتغيرات ثم شغّل عمال: python -m telegram_bot_engine.services.hosting.worker")
        return "\n".join(lines)


def market_gate_enabled() -> bool:
    if "TBE_MARKET_GATE" in os.environ:
        return _on("TBE_MARKET_GATE", "1")
    # Auto-on outside pure local/dev
    return _env() not in {"dev", "development", "local", "test"}


def evaluate_market_gate() -> GateResult:
    if not market_gate_enabled():
        return GateResult(ok=True, warnings=["market_gate_skipped_dev"])

    missing: list[str] = []
    warnings: list[str] = []

    secret = (os.environ.get("TBE_TOKEN_SECRET") or "").strip()
    if len(secret) < 32:
        missing.append("TBE_TOKEN_SECRET (32+ حرف)")

    if not (os.environ.get("TBE_DOCKER_NETWORK") or "").strip():
        missing.append("TBE_DOCKER_NETWORK (شبكة egress معزولة)")

    if not _on("TBE_SCALE_MODE", "0"):
        missing.append("TBE_SCALE_MODE=1 (طابور + workers — إلزامي للبيع)")

    db = (os.environ.get("TBE_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip().lower()
    if not (db.startswith("postgres://") or db.startswith("postgresql://")):
        missing.append("TBE_DATABASE_URL=postgresql://... (Postgres للتحكم)")

    registry = (os.environ.get("TBE_DOCKER_REGISTRY") or "").strip()
    if not registry:
        missing.append("TBE_DOCKER_REGISTRY (سجل صور مشترك بين العقد)")

    if not _on("TBE_DOCKER_PUSH", "0"):
        missing.append("TBE_DOCKER_PUSH=1")

    if _on("TBE_ALLOW_LOCAL_PROCESS", "0"):
        missing.append("TBE_ALLOW_LOCAL_PROCESS يجب أن يكون 0")

    if not _on("TBE_REQUIRE_DOCKER", "1"):
        warnings.append("TBE_REQUIRE_DOCKER ليس 1")

    # Fast check only (full daemon probe is the worker's job — avoids API hangs)
    import shutil
    if not shutil.which("docker"):
        missing.append("Docker CLI غير مثبت على هذه العقدة")

    return GateResult(ok=not missing, missing=missing, warnings=warnings)
