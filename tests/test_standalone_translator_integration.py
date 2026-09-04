"""Translate path retired — always None."""
from lumen.engine.services.translator_client import translate_request, chat_request


def test_translate_request_retired():
    assert translate_request("بوت متجر") is None
    assert translate_request("عايز أعمل بوت متجر فيه منتجات ودفع ومتابعة الطلب") is None


def test_chat_request_retired():
    assert chat_request("مرحبا") is None
