"""Hard guards: chat/token never become env; path must exist on disk."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod

mc = _load("lumen_bot_message_classify", "lumen/bot/message_classify.py")


def test_bot_token_not_env():
    tok = "123456789:AA" + ("x" * 35)
    c = mc.classify(tok, pending_env_var="RATE_LIMIT_SECONDS")
    assert c.kind == mc.MessageKind.BOT_TOKEN
    assert not mc.is_plausible_env_value("RATE_LIMIT_SECONDS", tok)


def test_arabic_chat_not_env():
    text = "اعمل بوت لما المستخدم يبعت ستارت يقول له تم استلام الرساله"
    c = mc.classify(text, pending_env_var="RATE_LIMIT_SECONDS")
    assert c.kind == mc.MessageKind.CHAT
    assert not mc.is_plausible_env_value("RATE_LIMIT_SECONDS", text)


def test_numeric_env_ok():
    assert mc.is_plausible_env_value("RATE_LIMIT_SECONDS", "30")
    c = mc.classify("30", pending_env_var="RATE_LIMIT_SECONDS")
    assert c.kind == mc.MessageKind.ENV_VALUE


def test_path_requires_existing_dir(tmp_path):
    missing = tmp_path / "gone"
    p = tmp_path / "repo"
    p.mkdir()
    assert mc.resolve_on_disk_path({"pending_repo_env": {"path": str(missing)}}) == ""
    assert mc.resolve_on_disk_path({"active_repo": {"path": str(p)}}) == str(p.resolve())
