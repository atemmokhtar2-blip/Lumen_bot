"""WhatsApp Cloud API bot scaffold — Meta official HTTP webhook pattern.

Uses requests against graph.facebook.com — no unofficial WhatsApp Web scrapers.
"""
from __future__ import annotations

from pathlib import Path

HANDLERS = '''"""WhatsApp Cloud API handlers."""
from __future__ import annotations

import logging
import os
from typing import Any

import requests

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v19.0"


def send_text(to: str, body: str) -> dict[str, Any]:
    token = os.environ.get("WHATSAPP_TOKEN") or os.environ.get("META_WA_TOKEN") or ""
    phone_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID") or ""
    if not token or not phone_id:
        return {"ok": False, "error": "missing_WHATSAPP_TOKEN_or_PHONE_NUMBER_ID"}
    url = f"{GRAPH}/{phone_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": body[:4096]},
    }
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 400:
        return {"ok": False, "status": resp.status_code, "body": (resp.text or "")[:500]}
    return {"ok": True, "data": resp.json()}


def handle_webhook_payload(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse Meta webhook and reply with echo (replace with product logic)."""
    results: list[dict[str, Any]] = []
    for entry in data.get("entry") or []:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for msg in value.get("messages") or []:
                if msg.get("type") != "text":
                    continue
                from_id = str(msg.get("from") or "")
                text = str((msg.get("text") or {}).get("body") or "")
                results.append(send_text(from_id, text or "OK"))
    return results
'''

MAIN = '''#!/usr/bin/env python3
"""WhatsApp Cloud API webhook server (Meta official)."""
from __future__ import annotations

import logging
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse
import json

from app.handlers import handle_webhook_payload

logging.basicConfig(level=logging.INFO)
VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN") or "lumen_verify"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        qs = parse_qs(urlparse(self.path).query)
        mode = (qs.get("hub.mode") or [""])[0]
        token = (qs.get("hub.verify_token") or [""])[0]
        challenge = (qs.get("hub.challenge") or [""])[0]
        if mode == "subscribe" and token == VERIFY_TOKEN:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(challenge.encode())
            return
        self.send_response(403)
        self.end_headers()

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(max(0, length))
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            data = {}
        handle_webhook_payload(data)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, fmt: str, *args) -> None:
        logging.info("%s - %s", self.address_string(), fmt % args)


def main() -> None:
    port = int(os.environ.get("PORT") or "8080")
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
'''


def write_whatsapp(root: Path) -> list[str]:
    written: list[str] = []
    (root / "app").mkdir(parents=True, exist_ok=True)
    files = {
        "main.py": MAIN,
        "app/__init__.py": '"""App package."""\n',
        "app/handlers.py": HANDLERS,
        "requirements.txt": "requests>=2.31.0\n",
        ".env.example": (
            "WHATSAPP_TOKEN=\n"
            "WHATSAPP_PHONE_NUMBER_ID=\n"
            "WHATSAPP_VERIFY_TOKEN=lumen_verify\n"
            "PORT=8080\n"
        ),
        "README.md": (
            "# WhatsApp Cloud API bot\n\n"
            "Uses Meta Graph API (official). Configure webhook to this server.\n\n"
            "```bash\nexport WHATSAPP_TOKEN=...\n"
            "export WHATSAPP_PHONE_NUMBER_ID=...\npython main.py\n```\n"
        ),
    }
    for rel, content in files.items():
        path = root / rel
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            written.append(rel)
    (root / "PLATFORM.md").write_text(
        "platform: whatsapp\nruntime: meta-cloud-api\n", encoding="utf-8"
    )
    written.append("PLATFORM.md")
    return written
