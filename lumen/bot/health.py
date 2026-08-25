"""Lightweight HTTP health server for Railway / container health checks."""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer

from .config import logger


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, format, *args):
        return  # silence access logs


def start_health_server(port: int) -> None:
    try:
        server = HTTPServer(("0.0.0.0", port), _HealthHandler)
        logger.info("Health server listening on 0.0.0.0:%s", port)
        server.serve_forever()
    except Exception as e:
        logger.warning("Health server failed: %s", e)
