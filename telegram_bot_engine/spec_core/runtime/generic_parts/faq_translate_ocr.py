def _faq_admin_ids() -> set[int]:
    import os as _os
    raw = (
        _os.getenv("FAQ_ADMIN_IDS")
        or _os.getenv("CAPABILITY_OPS_ADMINS")
        or _os.getenv("ADMIN_IDS")
        or ""
    )
    out: set[int] = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def _faq_is_admin(user_id: int) -> bool:
    import os as _os
    admins = _faq_admin_ids()
    if not admins:
        # open in dev unless FAQ_REQUIRE_ADMIN=1
        return (_os.getenv("FAQ_REQUIRE_ADMIN") or "0").strip().lower() not in {"1", "true", "yes", "on"}
    return int(user_id) in admins


def _faq_load_custom() -> list[tuple[str, str, int]]:
    """Load custom FAQ rows from domain_items (title=faq:question)."""
    ensure()
    rows = _list("content", user_id=None, status="open", limit=100)
    out: list[tuple[str, str, int]] = []
    for r in rows:
        # sqlite3.Row supports key access, not dict.get(). Keep this path
        # compatible with generated apps and custom row factories.
        try:
            title = (r["title"] or "")
            body = (r["body"] or "")
            row_id = int(r["id"])
        except (KeyError, IndexError, TypeError):
            title = (getattr(r, "get", lambda *_: "")("title") or "")
            body = (getattr(r, "get", lambda *_: "")("body") or "")
            row_id = int(getattr(r, "get", lambda *_: 0)("id") or 0)
        if title.startswith("faq:"):
            q = title[4:].strip()
            a = body.strip()
            if q and a and row_id:
                out.append((q, a, row_id))
    return out


def faq(user_id: int, text: str = "") -> str:
    """FAQ: list, search, admin add/delete. Seed + SQLite custom + FAQ_EXTRA_JSON."""
    ensure()
    import os as _os
    q = (text or "").strip()
    extra: list[tuple[str, str]] = []
    raw = (_os.getenv("FAQ_EXTRA_JSON") or "").strip()
    if raw:
        try:
            import json as _json
            data = _json.loads(raw)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and item.get("q") and item.get("a"):
                        extra.append((str(item["q"]), str(item["a"])))
        except Exception:
            pass
    custom = _faq_load_custom()
    items: list[tuple[str, str]] = list(_FAQ_SEED) + extra + [(c[0], c[1]) for c in custom]

    # Admin: /faq add سؤال | جواب
    low = q.lower()
    if low.startswith("add ") or q.startswith("أضف ") or q.startswith("اضف "):
        if not _faq_is_admin(user_id):
            return "⛔ إضافة FAQ للمشرفين فقط (FAQ_ADMIN_IDS / ADMIN_IDS)."
        payload = q.split(None, 1)[1] if " " in q else ""
        if "|" not in payload and "｜" not in payload:
            return "الصيغة: /faq add السؤال | الجواب"
        sep = "|" if "|" in payload else "｜"
        qq, aa = payload.split(sep, 1)
        qq, aa = qq.strip(), aa.strip()
        if not qq or not aa:
            return "السؤال والجواب مطلوبان."
        iid = _insert("content", int(user_id), f"faq:{qq[:120]}", aa[:2000], "open", {"kind": "faq_custom"})
        return f"✅ تمت إضافة FAQ #{iid}\nس: {qq[:80]}\nج: {aa[:120]}"

    # Admin: /faq del <id>
    if low.startswith("del ") or low.startswith("delete ") or q.startswith("حذف "):
        if not _faq_is_admin(user_id):
            return "⛔ حذف FAQ للمشرفين فقط."
        iid = _first_id(q.split(None, 1)[1] if " " in q else "")
        if not iid:
            return "حدد رقم العنصر: /faq del 12"
        with connect() as conn:
            cur = conn.execute(
                "UPDATE domain_items SET status='closed', updated_at=? WHERE id=? AND service='content' AND title LIKE 'faq:%'",
                (_now(), iid),
            )
            conn.commit()
            n = int(cur.rowcount)
        return f"تم حذف #{iid}" if n else f"غير موجود أو ليس FAQ: #{iid}"

    if not q or low in {"list", "all", "قائمة", "الكل", "مساعدة", "help"}:
        lines = ["❓ الأسئلة الشائعة:"]
        for i, (qq, aa) in enumerate(items, 1):
            lines.append(f"{i}. {qq}")
        if custom:
            lines.append("\n— مخصص (معرّفات):")
            for qq, aa, iid in custom[:15]:
                lines.append(f"  #{iid} {qq[:50]}")
        lines.append("\nابحث: /faq كلمة")
        if _faq_is_admin(user_id):
            lines.append("إضافة: /faq add سؤال | جواب")
            lines.append("حذف: /faq del <id>")
        _insert("content", int(user_id), "faq_list", q or "list", "done", {"count": len(items)})
        return "\n".join(lines)

    q_low = q.lower()
    hits = []
    for qq, aa in items:
        if q_low in qq.lower() or q_low in aa.lower() or q in qq or q in aa:
            hits.append((qq, aa))
    if not hits:
        lines = [
            f"❓ لم أجد تطابقاً لـ «{q[:40]}»",
            "جرّب /faq لعرض القائمة، أو أعد صياغة السؤال.",
        ]
        _insert("content", int(user_id), "faq_miss", q[:200], "done", {})
        return "\n".join(lines)

    lines = [f"❓ نتائج البحث ({len(hits)}):"]
    for qq, aa in hits[:5]:
        lines.append(f"• {qq}\n  → {aa}")
    _insert("content", int(user_id), "faq_hit", q[:200], "done", {"hits": len(hits)})
    return "\n".join(lines)



def translate_text(user_id: int, text: str = "") -> str:
    """Translation helper with optional production backends.

    Backends (TRANSLATE_BACKEND):
      echo (default)           — deterministic offline label
      deep-translator|google   — GoogleTranslator via deep-translator pkg
      libre|libretranslate     — HTTP LibreTranslate (TRANSLATE_API_URL)

    Never crashes if optional deps/network missing.
    """
    ensure()
    import os as _os
    text = (text or "").strip()
    if not text:
        return (
            "🌐 الترجمة\n"
            "الاستخدام: /translate مرحبا بك\n"
            "أو: /translate en:hello world\n"
            "الحالة: /translate status\n"
            "BACKENDS: echo | deep-translator | libre\n"
            "TRANSLATE_BACKEND=...  TRANSLATE_API_URL=...  TRANSLATE_API_KEY=..."
        )
    if text.lower() in {"status", "حالة", "backends", "health"}:
        return backend_status()
    target = (_os.getenv("TRANSLATE_TARGET") or "ar").strip().lower() or "ar"
    payload = text
    if ":" in text[:8]:
        maybe, rest = text.split(":", 1)
        if 1 <= len(maybe.strip()) <= 5 and maybe.strip().replace("-", "").isalpha():
            target = maybe.strip().lower()
            payload = rest.strip()
    if not payload:
        return "أدخل نصاً بعد رمز اللغة، مثال: /translate en:مرحبا"

    backend = (_os.getenv("TRANSLATE_BACKEND") or "echo").strip().lower()
    translated = None
    note = ""
    if backend in {"deep-translator", "deep_translator", "google"}:
        try:
            from deep_translator import GoogleTranslator  # type: ignore
            translated = GoogleTranslator(source="auto", target=target).translate(payload)
            note = "deep-translator"
        except Exception as exc:
            note = f"deep-translator failed:{type(exc).__name__}"
            translated = None
    elif backend in {"libre", "libretranslate"}:
        try:
            import json as _json
            from urllib import request as _urlreq
            api = (_os.getenv("TRANSLATE_API_URL") or "http://localhost:5000").rstrip("/")
            body = _json.dumps({
                "q": payload, "source": "auto", "target": target, "format": "text",
            }).encode("utf-8")
            headers = {"Content-Type": "application/json"}
            api_key = (_os.getenv("TRANSLATE_API_KEY") or "").strip()
            if api_key:
                headers["Authorization"] = f"Bearer {api_key}"
                # common alternate header used by some LibreTranslate hosts
                headers["api-key"] = api_key
            req = _urlreq.Request(
                api + "/translate",
                data=body,
                headers=headers,
                method="POST",
            )
            with _urlreq.urlopen(req, timeout=float(_os.getenv("TRANSLATE_TIMEOUT") or "8")) as resp:
                data = _json.loads(resp.read().decode("utf-8", errors="ignore"))
            translated = (data.get("translatedText") or data.get("translation") or "").strip()
            note = "libretranslate"
            if not translated:
                note = "libretranslate empty"
                translated = None
        except Exception as exc:
            note = f"libre failed:{type(exc).__name__}"
            translated = None

    if not translated:
        translated = f"[{target}] {payload}"
        backend = f"echo" + (f" ({note})" if note else "")
    else:
        backend = note or backend

    iid = _insert(
        "translate", int(user_id), f"to:{target}", payload,
        "done", {"backend": backend, "result": translated[:500]},
    )
    return (
        f"🌐 ترجمة #{iid}\n"
        f"→ {translated}\n"
        f"(backend: {backend})"
    )


def ocr_hint(user_id: int, text: str = "") -> str:
    """OCR helper — stores intent; optional pytesseract if available + path given."""
    ensure()
    text = (text or "").strip()
    iid = _insert("ocr", int(user_id), "ocr_hint", text or "awaiting_photo", "open", {"awaiting": "photo"})
    if text and len(text) > 5:
        return f"📝 OCR #{iid}\nالنص المستلم:\n{text[:1500]}"
    return (
        f"📝 OCR #{iid}\n"
        "أرسل صورة فيها نص الآن، أو الصق النص بعد الأمر.\n"
        "للتفعيل الكامل: pip install pytesseract + Tesseract OCR"
    )


def ocr_from_image(user_id: int, image_path: str = "", caption: str = "") -> str:
    """Run OCR on a local image path when pytesseract is available; else durable ack.

    Env:
      OCR_LANG=eng+ara (tesseract langs)
      OCR_ENABLED=1 (default on when deps exist)
    """
    ensure()
    import os as _os
    caption = (caption or "").strip()
    extracted = ""
    backend = "none"
    enabled = (_os.getenv("OCR_ENABLED") or "1").strip().lower() not in {"0", "false", "no"}
    if image_path and enabled:
        try:
            import pytesseract  # type: ignore
            from PIL import Image  # type: ignore
            lang = (_os.getenv("OCR_LANG") or "eng+ara").strip() or "eng"
            img = Image.open(image_path)
            extracted = (pytesseract.image_to_string(img, lang=lang) or "").strip()
            backend = f"pytesseract:{lang}"
        except Exception as exc:
            backend = f"unavailable:{type(exc).__name__}"
    if not extracted and caption:
        extracted = caption
        backend = "caption" if backend == "none" else f"{backend}+caption"
    iid = _insert(
        "ocr", int(user_id), "ocr_image",
        extracted[:2000] or (image_path or "no_text"),
        "done" if extracted else "open",
        {"backend": backend, "path": (image_path or "")[-120:]},
    )
    if extracted:
        return f"📝 OCR #{iid}\n{extracted[:2000]}"
    return (
        f"📝 OCR #{iid}\n"
        "تم حفظ الصورة. لم يُستخرج نص.\n"
        "ثبّت: pip install pytesseract Pillow  +  Tesseract OCR على النظام\n"
        f"backend={backend}"
    )


