#!/usr/bin/env python3
"""Lumen guest supervisor — permanent-host plane inside the microVM.

Contract (serial console markers — host polls these):
  lumen-guest-ready   — supervisor started, token+project resolved
  lumen-bot-started   — child bot process spawned
  lumen-bot-exit N    — child exited with code N (will restart unless permanent fail)
  lumen-bot-fatal     — supervisor giving up

Environment / files:
  /project              — project drive mount (required)
  /token/BOT_TOKEN or TELEGRAM_BOT_TOKEN env or MMDS
  LUMEN_BOT_ENTRY       — optional entry override
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

PROJECT = Path(os.environ.get("LUMEN_PROJECT_ROOT") or "/project")
TOKEN_DIR = Path(os.environ.get("LUMEN_TOKEN_DIR") or "/token")
MAX_RESTARTS = int(os.environ.get("LUMEN_BOT_MAX_RESTARTS") or "20")
RESTART_DELAY = float(os.environ.get("LUMEN_BOT_RESTART_DELAY") or "3")


def _log(msg: str) -> None:
    line = msg if msg.endswith("\n") else msg + "\n"
    try:
        sys.stdout.write(line)
        sys.stdout.flush()
    except Exception:
        pass
    try:
        sys.stderr.write(line)
        sys.stderr.flush()
    except Exception:
        pass


def _load_token() -> str:
    for key in ("TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    for name in ("BOT_TOKEN", "TELEGRAM_BOT_TOKEN"):
        p = TOKEN_DIR / name
        if p.is_file():
            return p.read_text(encoding="utf-8").strip()
    # MMDS link-local (Firecracker)
    try:
        req = urllib.request.Request(
            "http://169.254.169.254/latest/user-data",
            headers={"Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw) if raw.strip().startswith("{") else {}
        if isinstance(data, dict):
            for key in ("TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
                v = str(data.get(key) or "").strip()
                if v:
                    return v
            latest = data.get("latest") if isinstance(data.get("latest"), dict) else {}
            ud = latest.get("user-data") if isinstance(latest.get("user-data"), dict) else {}
            for key in ("TELEGRAM_BOT_TOKEN", "BOT_TOKEN"):
                v = str(ud.get(key) or "").strip()
                if v:
                    return v
    except Exception:
        pass
    return ""


def _find_entry() -> Path:
    hint = (os.environ.get("LUMEN_BOT_ENTRY") or "").strip()
    if hint:
        p = PROJECT / hint if not hint.startswith("/") else Path(hint)
        if p.is_file():
            return p
    for rel in ("main.py", "bot.py", "app.py", "src/main.py"):
        p = PROJECT / rel
        if p.is_file():
            return p
    raise FileNotFoundError("no_entry_main_py")


def _verify_token(token: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        with urllib.request.urlopen(url, timeout=15) as resp:
            body = json.loads(resp.read().decode("utf-8", errors="replace"))
        return bool(body.get("ok"))
    except Exception as exc:
        _log(f"lumen-token-check-failed {type(exc).__name__}")
        return False


def main() -> int:
    _log("lumen-guest-supervisor-start")
    if not PROJECT.is_dir():
        _log("lumen-bot-fatal project_missing")
        return 2
    token = _load_token()
    if not token:
        _log("lumen-bot-fatal token_missing")
        return 3
    os.environ["TELEGRAM_BOT_TOKEN"] = token
    os.environ["BOT_TOKEN"] = token
    # Host-prepared deps (pip --target on API/worker) — required when egress is Telegram-only
    extra_paths: list[str] = []
    host_deps = (os.environ.get("LUMEN_HOST_DEPS") or "").strip()
    if host_deps:
        extra_paths.append(host_deps)
    for rel in (".tbe_host_deps", ".tbe_deps"):
        pth = PROJECT / rel
        if pth.is_dir():
            extra_paths.append(str(pth))
    if extra_paths:
        prev = (os.environ.get("PYTHONPATH") or "").strip()
        merged = os.pathsep.join(extra_paths + ([prev] if prev else []))
        os.environ["PYTHONPATH"] = merged
        _log(f"lumen-pythonpath {merged}")
    try:
        entry = _find_entry()
    except FileNotFoundError:
        _log("lumen-bot-fatal entry_missing")
        return 4

    _log("lumen-guest-ready")
    if not _verify_token(token):
        _log("lumen-bot-fatal token_rejected_by_telegram")
        return 5

    restarts = 0
    while restarts <= MAX_RESTARTS:
        _log(f"lumen-bot-started entry={entry}")
        try:
            proc = subprocess.Popen(
                [sys.executable, str(entry)],
                cwd=str(PROJECT),
                env=os.environ.copy(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
            )
        except Exception as exc:
            _log(f"lumen-bot-fatal spawn:{type(exc).__name__}")
            return 6

        assert proc.stdout is not None
        try:
            for raw in iter(proc.stdout.readline, b""):
                try:
                    sys.stdout.buffer.write(raw)
                    sys.stdout.buffer.flush()
                except Exception:
                    break
        except Exception:
            pass
        code = proc.wait()
        _log(f"lumen-bot-exit {code}")
        if code == 0:
            return 0
        restarts += 1
        time.sleep(RESTART_DELAY)

    _log("lumen-bot-fatal max_restarts")
    return 7


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    raise SystemExit(main())
