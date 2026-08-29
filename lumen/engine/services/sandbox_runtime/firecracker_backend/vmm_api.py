"""Firecracker HTTP API over Unix socket."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

def _api_put(sock: Path, path: str, body: dict, timeout: float = 15.0) -> None:
    data = json.dumps(body)
    # Prefer curl unix-socket (ubiquitous); fallback to Python http if needed.
    if shutil.which("curl"):
        r = subprocess.run(
            [
                "curl",
                "--unix-socket",
                str(sock),
                "-sS",
                "-X",
                "PUT",
                f"http://localhost{path}",
                "-H",
                "Content-Type: application/json",
                "-d",
                data,
            ],
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if r.returncode != 0:
            raise RuntimeError(f"fc_api_put_failed:{path}:{(r.stderr or b'')!r}")
        return
    # Minimal fallback without third-party deps
    import http.client
    import socket as _socket

    class _UnixHTTPConnection(http.client.HTTPConnection):
        def __init__(self, socket_path: str) -> None:
            super().__init__("localhost")
            self._socket_path = socket_path

        def connect(self) -> None:
            self.sock = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            self.sock.connect(self._socket_path)

    conn = _UnixHTTPConnection(str(sock))
    try:
        conn.request("PUT", path, body=data, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        if resp.status >= 300:
            raise RuntimeError(f"fc_api_put_http:{path}:{resp.status}")
    finally:
        conn.close()


