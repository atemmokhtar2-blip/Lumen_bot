"""Detect target platform and apply the matching official scaffold."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from . import discord_scaffold, telegram_scaffold, whatsapp_scaffold

_PLATFORMS = ("telegram", "discord", "whatsapp", "web")


def supported_platforms() -> list[str]:
    return list(_PLATFORMS)


def detect_platform(text: str = "", *, explicit: str = "") -> str:
    forced = (explicit or os.getenv("LUMEN_TARGET_PLATFORM") or "").strip().lower()
    if forced in _PLATFORMS:
        return forced
    t = (text or "").lower()
    # Arabic + English cues
    if re.search(r"discord|ديسكورد", t):
        return "discord"
    if re.search(r"whatsapp|واتس|واتساب", t):
        return "whatsapp"
    if re.search(r"\bweb\b|website|موقع|site\b|dashboard", t):
        return "web"
    if re.search(r"telegram|تيليجرام|تلجرام", t):
        return "telegram"
    return "telegram"  # default remains TG until product routing changes


def apply_platform_scaffold(
    project_path: str | Path,
    *,
    platform: str = "",
    user_text: str = "",
) -> dict[str, Any]:
    root = Path(project_path)
    root.mkdir(parents=True, exist_ok=True)
    plat = detect_platform(user_text, explicit=platform)
    written: list[str] = []
    if plat == "discord":
        written = discord_scaffold.write_discord(root)
    elif plat == "whatsapp":
        written = whatsapp_scaffold.write_whatsapp(root)
    elif plat == "web":
        # minimal ASGI-ish stub toward sites/apps
        written = _write_web(root)
    else:
        written = telegram_scaffold.write_telegram(root)
    return {
        "ok": True,
        "platform": plat,
        "written": written,
        "engine": "platform_generators",
    }


def _write_web(root: Path) -> list[str]:
    written: list[str] = []
    main = '''#!/usr/bin/env python3
"""Minimal web app entry — expand into full site/dashboard."""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
import os


class H(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = b"<h1>Lumen web app</h1><p>Replace with your product UI/API.</p>"
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    port = int(os.environ.get("PORT") or "8000")
    HTTPServer(("0.0.0.0", port), H).serve_forever()


if __name__ == "__main__":
    main()
'''
    files = {
        "main.py": main,
        "requirements.txt": "# add fastapi/uvicorn when scaling the web surface\n",
        ".env.example": "PORT=8000\n",
        "README.md": "# Web app scaffold\n\n```bash\npython main.py\n```\n",
        "PLATFORM.md": "platform: web\nruntime: stdlib-http\n",
    }
    for rel, content in files.items():
        path = root / rel
        if not path.exists():
            path.write_text(content, encoding="utf-8")
            written.append(rel)
    return written


__all__ = ["detect_platform", "apply_platform_scaffold", "supported_platforms"]
