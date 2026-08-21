"""Phase-2 hybrid scaffolds — fill declared gaps without full Cline.

When engine_mode=hybrid and capabilities_gap includes known integration
labels, write safe stub modules the bot can grow into (no live secrets).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_WEBHOOK = '''"""Webhook receiver scaffold — fill endpoint logic later.

Set WEBHOOK_SECRET in .env before exposing publicly.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any


def verify_signature(body: bytes, header_sig: str | None) -> bool:
    secret = (os.getenv("WEBHOOK_SECRET") or "").encode()
    if not secret or not header_sig:
        return False
    digest = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, header_sig.replace("sha256=", ""))


def handle_event(payload: dict[str, Any]) -> dict[str, Any]:
    """Return ack; replace with domain logic (Stripe, CRM, …)."""
    event = str(payload.get("type") or payload.get("event") or "unknown")
    return {"ok": True, "received": event}
'''

_HTTP_TOOL = '''"""External HTTP tool scaffold — for gap integrations.

Never log secrets. Configure BASE_URL + API_KEY via environment.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def call_json(
    path: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 20.0,
) -> dict[str, Any]:
    base = (os.getenv("EXTERNAL_API_BASE") or "").rstrip("/")
    if not base:
        return {"ok": False, "error": "EXTERNAL_API_BASE not configured"}
    url = f"{base}/{path.lstrip('/')}"
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method.upper())
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    key = (os.getenv("EXTERNAL_API_KEY") or "").strip()
    if key:
        req.add_header("Authorization", f"Bearer {key}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                parsed = {"raw": raw[:2000]}
            return {"ok": True, "status": getattr(resp, "status", 200), "data": parsed}
    except urllib.error.HTTPError as exc:
        body_txt = exc.read()[:500].decode("utf-8", errors="replace")
        return {"ok": False, "error": f"http_{exc.code}", "body": body_txt}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}
'''

_CRON = '''"""Scheduler scaffold — document intended jobs (not a live daemon).

Wire to your host cron / worker to call these functions.
"""
from __future__ import annotations

JOBS: dict[str, str] = {}


def register(name: str, schedule: str) -> None:
    JOBS[name] = schedule


def list_jobs() -> dict[str, str]:
    return dict(JOBS)
'''


def apply_hybrid_scaffolds(
    project_path: str | Path,
    gaps: list[str],
    metadata: dict[str, Any] | None = None,
) -> list[str]:
    """Write scaffold modules for known gap labels. Returns relative paths written."""
    root = Path(project_path)
    app = root / "app"
    if not app.is_dir():
        return []
    services = app / "services"
    services.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    gap_set = {str(g).strip().lower() for g in gaps if str(g).strip()}

    def _write(rel: str, content: str) -> None:
        path = root / rel
        if path.exists():
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        written.append(rel)

    if gap_set & {
        "webhook",
        "payment_gateway",
        "external_integration",
        "external_api",
    }:
        _write("app/services/webhook_scaffold.py", _WEBHOOK)
    if gap_set & {
        "llm_api",
        "external_api",
        "external_integration",
        "payment_gateway",
    }:
        _write("app/services/http_tool.py", _HTTP_TOOL)
    if gap_set & {"cron", "scheduler", "out_of_catalog"}:
        _write("app/services/cron_scaffold.py", _CRON)

    if written:
        logger.info("hybrid scaffolds written: %s gaps=%s", written, sorted(gap_set))
        note = root / "HYBRID_GAPS.md"
        if not note.exists():
            lines = [
                "# Hybrid gaps",
                "",
                "Catalog compose + scaffolds for:",
                "",
            ]
            for g in sorted(gap_set):
                lines.append(f"- `{g}`")
            lines.extend(
                [
                    "",
                    "Env: `WEBHOOK_SECRET`, `EXTERNAL_API_BASE`, `EXTERNAL_API_KEY`.",
                    "Cline can later replace scaffolds under policy.",
                    "",
                ]
            )
            note.write_text("\n".join(lines), encoding="utf-8")
            written.append("HYBRID_GAPS.md")
        env_ex = root / "ENV.example"
        if not env_ex.exists():
            env_ex.write_text(
                "\n".join(
                    [
                        "# Hybrid / integration env",
                        "WEBHOOK_SECRET=",
                        "EXTERNAL_API_BASE=",
                        "EXTERNAL_API_KEY=",
                        "ACTIVEPIECES_WEBHOOK_BASE=",
                        "ACTIVEPIECES_TOKEN=",
                        "",
                    ]
                ),
                encoding="utf-8",
            )
            written.append("ENV.example")
    return written


__all__ = ["apply_hybrid_scaffolds"]
