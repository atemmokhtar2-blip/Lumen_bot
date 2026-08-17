def backend_status() -> str:
    """Report which optional backends are configured and importable."""
    import os as _os
    lines = ["🔧 حالة الـ backends"]
    # translate
    tb = (_os.getenv("TRANSLATE_BACKEND") or "echo").strip().lower()
    lines.append(f"TRANSLATE_BACKEND={tb}")
    if tb in {"deep-translator", "deep_translator", "google"}:
        try:
            import deep_translator  # type: ignore  # noqa: F401
            lines.append("  deep-translator: available")
        except Exception as exc:
            lines.append(f"  deep-translator: MISSING ({type(exc).__name__})")
    if tb in {"libre", "libretranslate"}:
        lines.append(f"  TRANSLATE_API_URL={(_os.getenv('TRANSLATE_API_URL') or '')[:60]}")
        lines.append(f"  TRANSLATE_API_KEY={'set' if (_os.getenv('TRANSLATE_API_KEY') or '').strip() else 'unset'}")
    # ocr
    ocr_on = (_os.getenv("OCR_ENABLED") or "1").strip().lower() not in {"0", "false", "no"}
    lines.append(f"OCR_ENABLED={1 if ocr_on else 0} lang={_os.getenv('OCR_LANG') or 'eng+ara'}")
    try:
        import pytesseract  # type: ignore  # noqa: F401
        from PIL import Image  # type: ignore  # noqa: F401
        lines.append("  pytesseract+Pillow: available")
    except Exception as exc:
        lines.append(f"  pytesseract+Pillow: MISSING ({type(exc).__name__})")
    return "\n".join(lines)




def voice_intake(user_id: int, text: str = "") -> str:
    """Record voice-note intent (no STT). Durable row for later processing.

    Ready for a future STT backend (VOICE_STT_BACKEND env). Currently
    acknowledges and stores; generated bots attach filters.VOICE via voice_from_file.
    """
    ensure()
    import os as _os
    text = (text or "").strip() or "voice_note_received"
    backend = (_os.getenv("VOICE_STT_BACKEND") or "none").strip().lower()
    iid = _insert(
        "voice", int(user_id), "voice_intake", text[:500], "open",
        {"kind": "voice", "stt_backend": backend},
    )
    if backend in {"none", "", "off"}:
        return (
            f"🎤 ملاحظة صوتية #{iid}\n"
            "تم تسجيل الطلب.\n"
            "أرسل رسالة صوتية مباشرة وسيتم حفظ الملف.\n"
            "STT اختياري عبر VOICE_STT_BACKEND."
        )
    return (
        f"🎤 ملاحظة صوتية #{iid}\n"
        f"تم التسجيل (backend={backend}).\n"
        "المعالجة قيد الانتظار."
    )


def voice_from_file(user_id: int, file_path: str = "", file_id: str = "", duration: int = 0) -> str:
    """Persist an incoming voice/audio file path for later STT processing."""
    ensure()
    import os as _os
    backend = (_os.getenv("VOICE_STT_BACKEND") or "none").strip().lower()
    meta = {
        "kind": "voice_file",
        "file_path": (file_path or "")[-200:],
        "file_id": (file_id or "")[:120],
        "duration": int(duration or 0),
        "stt_backend": backend,
    }
    title = f"voice:{file_id[:24]}" if file_id else "voice_file"
    body = file_path or file_id or "voice_received"
    iid = _insert("voice", int(user_id), title, body[:500], "open", meta)
    # Optional: placeholder for external STT — never crash if missing
    transcript = ""
    if backend not in {"none", "", "off"} and file_path and _os.path.isfile(file_path):
        try:
            # Hook only — real STT providers wired later via env
            transcript = f"[stt:{backend} pending]"
        except Exception as exc:
            transcript = f"[stt_error:{type(exc).__name__}]"
    if transcript:
        return (
            f"🎤 صوت #{iid}\n"
            f"المدة: {duration or '?'}ث\n"
            f"{transcript}\n"
            "تم حفظ الملف للمعالجة."
        )
    return (
        f"🎤 صوت #{iid}\n"
        f"تم حفظ الرسالة الصوتية (مدة {duration or '?'}ث).\n"
        "للتفريغ النصي لاحقاً: VOICE_STT_BACKEND=..."
    )


def payment_info(user_id: int, text: str = "") -> str:
    """Show manual payment instructions from env; never embeds secrets in code."""
    ensure()
    import os as _os
    lines = ["💳 طرق الدفع اليدوي"]
    vcash = (_os.getenv("PAYMENT_VODAFONE_CASH") or "").strip()
    bank = (_os.getenv("PAYMENT_BANK_IBAN") or "").strip()
    instapay = (_os.getenv("PAYMENT_INSTAPAY") or "").strip()
    wallet = (_os.getenv("PAYMENT_WALLET") or "").strip()
    note = (_os.getenv("PAYMENT_INSTRUCTIONS") or "").strip()
    if vcash:
        lines.append(f"فودافون كاش: {vcash}")
    if instapay:
        lines.append(f"InstaPay: {instapay}")
    if bank:
        lines.append(f"تحويل بنكي: {bank}")
    if wallet:
        lines.append(f"محفظة: {wallet}")
    if note:
        lines.append(note)
    if len(lines) == 1:
        lines.append(
            "لم تُضبط بعد.\n"
            "ضع في .env:\n"
            "  PAYMENT_VODAFONE_CASH=\n"
            "  PAYMENT_INSTAPAY=\n"
            "  PAYMENT_BANK_IBAN=\n"
            "  PAYMENT_WALLET=\n"
            "  PAYMENT_INSTRUCTIONS="
        )
    body = "\n".join(lines)
    _insert("payments", int(user_id), "payment_info", (text or "")[:200], "done", {"view": True})
    return body


# Default FAQ seed + durable custom rows (service=content, title starts with faq:)
_FAQ_SEED: list[tuple[str, str]] = [
    (str(item[0]), str(item[1]))
    for item in (_RUNTIME_DATA.get("_FAQ_SEED") or [])
    if isinstance(item, (list, tuple)) and len(item) >= 2
]


