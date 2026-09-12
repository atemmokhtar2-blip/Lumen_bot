"""Firecracker HTTP API over Unix socket (single client for all FC modules)."""
from __future__ import annotations

import json
import logging
import shutil
import socket
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)


def api_request(
    sock: Path,
    method: str,
    path: str,
    body: dict | None = None,
    *,
    timeout: float = 30.0,
) -> None:
    """PUT/PATCH/GET against Firecracker API socket. Fails closed on non-2xx."""
    method = (method or "PUT").upper()
    data = json.dumps(body or {})
    if shutil.which("curl"):
        r = subprocess.run(
            [
                "curl",
                "--unix-socket",
                str(sock),
                "-sS",
                "-X",
                method,
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
            err = (r.stderr or b"")
            raise RuntimeError(f"fc_api_{method.lower()}_failed:{path}:{err!r}")
        return

    payload = data.encode("utf-8")
    req = (
        f"{method} {path} HTTP/1.1\r\n"
        f"Host: localhost\r\n"
        f"Content-Type: application/json\r\n"
        f"Accept: application/json\r\n"
        f"Content-Length: {len(payload)}\r\n"
        f"\r\n"
    ).encode("utf-8") + payload
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock))
        s.sendall(req)
        chunks: list[bytes] = []
        while True:
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            chunks.append(chunk)
            joined = b"".join(chunks)
            if b"\r\n\r\n" in joined:
                try:
                    s.settimeout(0.2)
                    while True:
                        more = s.recv(4096)
                        if not more:
                            break
                        chunks.append(more)
                except (socket.timeout, OSError):
                    pass
                break
    raw = b"".join(chunks).decode("utf-8", errors="replace")
    if "HTTP/1.1 2" not in raw and "HTTP/1.0 2" not in raw:
        raise RuntimeError(f"fc_api_error:{method}:{path}:{raw[:300]}")


def api_put(sock: Path, path: str, body: dict, *, timeout: float = 30.0) -> None:
    api_request(sock, "PUT", path, body, timeout=timeout)


def api_patch(sock: Path, path: str, body: dict, *, timeout: float = 30.0) -> None:
    api_request(sock, "PATCH", path, body, timeout=timeout)


_api_put = api_put
_api_patch = api_patch

__all__ = ["api_request", "api_put", "api_patch", "_api_put", "_api_patch"]
