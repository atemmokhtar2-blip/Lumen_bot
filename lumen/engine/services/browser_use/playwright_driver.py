"""Real Playwright browser automation for agent computer-use.

Uses the official ``playwright`` Python package (Chromium).
Requires: pip install playwright && playwright install chromium

Env:
  BROWSER_USE_ENABLED=1          — allow browser tools (default off for safety)
  BROWSER_USE_HEADLESS=1         — headless (default 1)
  BROWSER_USE_TIMEOUT_MS=30000
  BROWSER_USE_MAX_PAGES=4
"""
from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_SESSIONS: dict[str, "BrowserSession"] = {}


def is_playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        from playwright.sync_api import sync_playwright  # noqa: F401
        return True
    except Exception:
        return False


def _enabled() -> bool:
    return (os.getenv("BROWSER_USE_ENABLED") or "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _headless() -> bool:
    return (os.getenv("BROWSER_USE_HEADLESS") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }


def _timeout_ms() -> int:
    try:
        return max(5000, min(120_000, int(os.getenv("BROWSER_USE_TIMEOUT_MS") or "30000")))
    except ValueError:
        return 30_000


def _max_pages() -> int:
    try:
        return max(1, min(8, int(os.getenv("BROWSER_USE_MAX_PAGES") or "4")))
    except ValueError:
        return 4


@dataclass
class BrowserSession:
    session_id: str
    work_dir: str = ""
    created_at: float = field(default_factory=time.time)
    _pw: Any = field(default=None, repr=False)
    _browser: Any = field(default=None, repr=False)
    _context: Any = field(default=None, repr=False)
    _page: Any = field(default=None, repr=False)

    def ensure(self) -> None:
        if self._page is not None:
            return
        if not is_playwright_available():
            raise RuntimeError(
                "playwright_not_installed: pip install playwright && playwright install chromium"
            )
        from playwright.sync_api import sync_playwright

        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=_headless())
        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            ignore_https_errors=False,
        )
        self._page = self._context.new_page()
        self._page.set_default_timeout(_timeout_ms())

    def close(self) -> None:
        for obj in (self._context, self._browser):
            try:
                if obj is not None:
                    obj.close()
            except Exception:
                pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass
        self._page = self._context = self._browser = self._pw = None


def _get_or_create(session_id: str | None = None, work_dir: str = "") -> BrowserSession:
    if not _enabled():
        raise RuntimeError("browser_use_disabled: set BROWSER_USE_ENABLED=1")
    with _LOCK:
        if session_id and session_id in _SESSIONS:
            return _SESSIONS[session_id]
        if len(_SESSIONS) >= _max_pages() and not session_id:
            # evict oldest
            oldest = sorted(_SESSIONS.values(), key=lambda s: s.created_at)[0]
            oldest.close()
            _SESSIONS.pop(oldest.session_id, None)
        sid = session_id or f"br-{uuid.uuid4().hex[:12]}"
        sess = BrowserSession(session_id=sid, work_dir=work_dir or "")
        sess.ensure()
        _SESSIONS[sid] = sess
        return sess


def close_session(session_id: str) -> dict[str, Any]:
    with _LOCK:
        sess = _SESSIONS.pop(session_id, None)
    if sess is None:
        return {"ok": False, "error": "session_not_found"}
    sess.close()
    return {"ok": True, "session_id": session_id}


def browse_url(
    url: str,
    *,
    session_id: str | None = None,
    work_dir: str = "",
    wait_until: str = "domcontentloaded",
) -> dict[str, Any]:
    """Navigate to URL with real Chromium via Playwright."""
    u = (url or "").strip()
    if not u.startswith(("http://", "https://")):
        return {"ok": False, "error": "url_must_be_http_https"}
    try:
        sess = _get_or_create(session_id, work_dir=work_dir)
        page = sess._page
        assert page is not None
        page.goto(u, wait_until=wait_until, timeout=_timeout_ms())
        title = page.title()
        return {
            "ok": True,
            "session_id": sess.session_id,
            "url": page.url,
            "title": title,
            "engine": "playwright_chromium",
        }
    except Exception as exc:
        logger.exception("browse_url failed")
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def get_content(session_id: str, *, max_chars: int = 12_000) -> dict[str, Any]:
    try:
        sess = _get_or_create(session_id)
        page = sess._page
        assert page is not None
        text = page.inner_text("body")
        html = page.content()
        return {
            "ok": True,
            "session_id": session_id,
            "url": page.url,
            "title": page.title(),
            "text": (text or "")[:max_chars],
            "html_len": len(html or ""),
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def click(session_id: str, selector: str) -> dict[str, Any]:
    try:
        sess = _get_or_create(session_id)
        page = sess._page
        assert page is not None
        page.click(selector, timeout=_timeout_ms())
        return {"ok": True, "session_id": session_id, "selector": selector, "url": page.url}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def fill(session_id: str, selector: str, value: str) -> dict[str, Any]:
    try:
        sess = _get_or_create(session_id)
        page = sess._page
        assert page is not None
        page.fill(selector, value or "", timeout=_timeout_ms())
        return {"ok": True, "session_id": session_id, "selector": selector}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def screenshot(
    session_id: str,
    *,
    path: str | None = None,
    full_page: bool = True,
) -> dict[str, Any]:
    try:
        sess = _get_or_create(session_id)
        page = sess._page
        assert page is not None
        out = path
        if not out:
            base = Path(sess.work_dir or ".") / "browser_screenshots"
            base.mkdir(parents=True, exist_ok=True)
            out = str(base / f"{sess.session_id}-{int(time.time())}.png")
        page.screenshot(path=out, full_page=full_page)
        return {
            "ok": True,
            "session_id": session_id,
            "path": out,
            "url": page.url,
            "engine": "playwright_chromium",
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}:{exc}"}


def status() -> dict[str, Any]:
    return {
        "enabled": _enabled(),
        "playwright_importable": is_playwright_available(),
        "headless": _headless(),
        "open_sessions": len(_SESSIONS),
        "max_pages": _max_pages(),
        "timeout_ms": _timeout_ms(),
    }


__all__ = [
    "BrowserSession",
    "browse_url",
    "click",
    "close_session",
    "fill",
    "get_content",
    "is_playwright_available",
    "screenshot",
    "status",
]
