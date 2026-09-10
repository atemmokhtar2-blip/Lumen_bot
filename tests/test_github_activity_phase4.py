"""Phase 4: activity log + scrub secrets."""
from __future__ import annotations

from lumen.engine.services.integrations.github import activity_log as al


def test_record_and_list_local(monkeypatch):
    monkeypatch.setattr(al, "_redis", lambda: None)
    with al._lock:
        al._local.clear()
    al.record(42, "connected", detail={"login": "octo", "token": "SECRET"})
    al.record(42, "repo_imported", detail={"full_name": "o/r"})
    rows = al.list_recent(42, limit=5)
    assert len(rows) == 2
    assert rows[0]["event"] == "repo_imported"
    assert "token" not in (rows[1].get("detail") or {})
    assert (rows[1].get("detail") or {}).get("login") == "octo"


def test_format_activity_ar(monkeypatch):
    monkeypatch.setattr(al, "_redis", lambda: None)
    with al._lock:
        al._local.clear()
    al.record(7, "push", detail={"path": "/tmp/x"})
    text = al.format_activity_ar(7)
    assert "سجل نشاط" in text
    assert "دفع" in text or "push" in text


def test_scrub_blocks_token_keys():
    d = al._scrub_detail({"token": "x", "installation_id": "1", "full_name": "a/b"})
    assert "token" not in d
    assert d.get("installation_id") == "1"
    assert d.get("full_name") == "a/b"
