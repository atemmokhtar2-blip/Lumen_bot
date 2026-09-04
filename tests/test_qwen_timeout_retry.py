"""Retired: Qwen translator HTTP path no longer exists."""
import importlib


def test_no_translate_request_symbol():
    mod = importlib.import_module("lumen.engine.services.translator_client")
    assert not hasattr(mod, "translate_request")
    assert not hasattr(mod, "requests")  # no HTTP client on this module
