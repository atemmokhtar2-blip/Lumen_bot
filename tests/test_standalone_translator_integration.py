"""Phase 0: translate/chat symbols must not exist on the generation path."""
import importlib
import inspect


def test_translator_client_has_no_llm_entrypoints():
    mod = importlib.import_module("lumen.engine.services.translator_client")
    forbidden = {
        "translate_request",
        "chat_request",
        "translate_via_groq",
        "chat_via_gemini",
        "translate_infinite_via_gemini",
        "translate_infinite_via_groq",
    }
    names = set(dir(mod))
    leaked = forbidden & names
    assert not leaked, f"dead LLM symbols still exported: {leaked}"
    src = inspect.getsource(mod)
    for name in forbidden:
        assert f"def {name}" not in src, f"def {name} still in translator_client"


def test_rule_helpers_still_work():
    from lumen.engine.services.translator_client import (
        _rule_features_from_text,
        _spec_core_capabilities,
    )
    caps = set(_spec_core_capabilities()) or {"welcome_set", "user_ban", "start", "help"}
    feats = _rule_features_from_text("بوت جروب ترحيب وحظر", caps)
    assert isinstance(feats, list)
