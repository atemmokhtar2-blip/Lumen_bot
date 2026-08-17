def _apply_exclusive_intent_locks(scores: dict[str, float], request: str) -> dict[str, float]:
    """Foundation conflict engine for preset scoring (Phase B root).

    1) Honour domain_detector.decide() blocked presets (authority from Phase A).
    2) Inside each exclusive family, keep the winner; zero the losers when
       margin is clear OR when anchors prove the intent.
    3) Pure tasks text (task anchors, no medical/booking anchors) always
       zeroes clinic/booking regardless of residual keyword noise.
    """
    out = dict(scores)
    t = _norm(request or "")

    # Domain-layer vetoes
    try:
        from .domain_detector import decide as _domain_decide
        dec = _domain_decide(request)
        for bp in dec.blocked_presets:
            out[bp] = 0.0
        if dec.primary in {"tasks", "projects"} and dec.confidence >= 0.45:
            for kill in (
                "booking", "clinic", "shop", "commerce_pro", "marketplace",
                "hr", "fitness", "restaurant", "auction", "delivery",
            ):
                out[kill] = 0.0
            out["tasks"] = max(out.get("tasks", 0.0), 10.0)
            return {k: v for k, v in out.items() if v > 0}
    except Exception:
        pass

    task_n = sum(1 for k in _TASK_ANCHORS if k in t)
    medical = any(k in t for k in _MEDICAL_ANCHORS)
    booking_a = any(k in t for k in _BOOKING_ANCHORS)

    if task_n >= 1 and not medical and not booking_a:
        out["booking"] = 0.0
        out["clinic"] = 0.0
        out["tasks"] = max(out.get("tasks", 0.0), 6.0 + 2.0 * task_n)

    # Winner-takes-family when one preset clearly leads
    for family in _EXCLUSIVE_FAMILIES:
        present = [(n, out.get(n, 0.0)) for n in family if out.get(n, 0.0) > 0]
        if len(present) < 2:
            continue
        present.sort(key=lambda x: -x[1])
        winner, wscore = present[0]
        second = present[1][1]
        # Clear margin OR tasks/clinic special cases
        if wscore >= second * 1.15 or (winner == "tasks" and task_n >= 1 and not medical):
            for n, _ in present[1:]:
                if winner == "tasks" and n in {"booking", "clinic"}:
                    out[n] = 0.0
                elif winner == "clinic" and n == "tasks" and medical:
                    out[n] = 0.0
                elif wscore >= second * 1.25:
                    out[n] = 0.0


    # Hard gate: booking/clinic scores from LU/arabic_intent cannot stand
    # without concrete anchors in the request text.
    if not medical:
        out["clinic"] = 0.0
    if not booking_a and not medical:
        out["booking"] = 0.0
    return {k: v for k, v in out.items() if v > 0}


def score_presets(request: str) -> list[tuple[str, float]]:
    """Rank preset intents by keyword evidence (multi-intent aware)."""
    scores: dict[str, float] = {}

    def add(name: str, keys: Iterable[str], weight: float = 1.0) -> None:
        s = _score_keys(request, keys, weight)
        if s > 0:
            scores[name] = scores.get(name, 0.0) + s

    # Higher weights for explicit product packs
    add("commerce_pro", _COMMERCE_PRO_KEYS, 3.0)
    add("creator", _CREATOR_KEYS, 2.2)
    add("saas", _SAAS_KEYS, 2.4)
    add("marketplace", _MARKETPLACE_KEYS, 2.3)
    add("logistics", _LOGISTICS_KEYS, 2.3)
    add("finance", _FINANCE_KEYS, 2.2)
    add("restaurant", _RESTAURANT_KEYS, 2.0)
    add("jobs", _JOBS_KEYS, 1.8)
    add("education", _EDU_KEYS, 1.8)
    add("events", _EVENTS_KEYS, 1.6)
    add("wallet", _WALLET_KEYS, 1.6)
    add("growth", _GROWTH_KEYS, 1.6)
    add("crm", _CRM_KEYS, 1.6)
    add("community", _COMMUNITY_KEYS, 1.5)
    add("contests", _CONTEST_KEYS, 1.5)
    add("subscriptions", _SUB_KEYS, 1.5)
    add("points", _POINTS_KEYS, 1.4)
    add("shop", _SHOP_KEYS, 1.4)
    add("community", ("اخبار", "أخبار", "news", "نشرة", "feed", "headline"), 1.3)
    add("support_pro", _SUPPORT_PRO_KEYS, 1.5)
    add("group_management", _GROUP_KEYS, 2.8)
    add("support_tickets", _SUPPORT_KEYS, 1.2)
    add("tasks", _TASK_KEYS, 2.6)
    add("notes", _NOTES_KEYS, 1.2)
    add("security_ops", _SECURITY_KEYS, 2.8)
    add("booking", _BOOK_KEYS, 1.1)
    add("hr", _HR_KEYS, 1.2)
    add("fitness", _FITNESS_KEYS, 1.9)
    add("realestate", _REALESTATE_KEYS, 1.9)
    add("clinic", _CLINIC_KEYS, 1.9)
    add("auction", _AUCTION_KEYS, 1.7)
    add("delivery", _DELIVERY_KEYS, 1.6)
    add("iot", _IOT_KEYS, 2.6)
    add("blockchain", _BLOCKCHAIN_KEYS, 2.5)
    add("ai_assist", _AI_KEYS, 2.2)
    add("devops", _DEVOPS_KEYS, 2.4)
    add("gaming", _GAMING_KEYS, 2.0)

    # ── Composite commerce_pro detection (Arabic-first multi-domain) ──
    # Count independent commerce pillars present in the request text.
    text_l = (request or "").lower()
    pillars = {
        "shop": any(k in text_l for k in ("متجر", "shop", "store", "ecommerce")),
        "catalog": any(k in text_l for k in ("كتالوج", "catalog", "منتجات", "product", "products")),
        "cart": any(k in text_l for k in ("سلة", "cart", "checkout", "إتمام شراء")),
        "orders": any(k in text_l for k in ("طلب", "طلبات", "تتبع", "إلغاء", "الغاء", "استرجاع", "استرداد", "order", "refund", "فاتورة", "فواتير")),
        "payments": any(k in text_l for k in ("دفع", "مدفوعات", "payment", "invoice", "فواتير")),
        "subs": any(k in text_l for k in ("اشتراك", "اشتراكات", "خطة", "خطط", "تجربة مجانية", "تجديد", "إهداء", "subscription", "trial", "renew")),
        "points": any(k in text_l for k in ("نقاط", "ولاء", "متصدرين", "مستويات", "points", "loyalty", "leaderboard")),
        "wallet": any(k in text_l for k in ("محفظة", "رصيد", "شحن", "wallet", "balance")),
        "growth": any(k in text_l for k in ("إحالة", "احالة", "دعوة", "سلاسل", "تسجيل يومي", "referral", "streak", "check-in", "checkin")),
        "contests": any(k in text_l for k in ("مسابقة", "مسابقات", "سحب", "contest", "giveaway", "raffle")),
        "analytics": any(k in text_l for k in ("تحليلات", "إيرادات", "ايرادات", "إذاعة", "اذاعة", "شرائح", "broadcast", "segment", "analytics")),
        "support": any(k in text_l for k in ("تذكرة", "تذاكر", "دعم", "قاعدة معرفة", "ticket", "knowledge")),
        "i18n": any(k in text_l for k in (
            "ترجمة", "تعدد لغات", "متعدد اللغات", "عربي وانجليزي", "انجليزي وعربي",
            "/lang", "i18n", "multilingual", "language pack", "تبديل اللغة",
        )),
        "admin": any(k in text_l for k in ("أدمن", "ادمن", "صيانة", "مخزون", "admin", "maintenance")),
    }
    pillar_count = sum(1 for v in pillars.values() if v)
    commerce_hits = sum(
        1
        for k in ("subscriptions", "points", "wallet", "growth", "contests", "support_tickets", "support_pro")
        if scores.get(k, 0) > 0
    )
    # Explicit suite phrase or many pillars → strong commerce_pro
    if scores.get("commerce_pro", 0) > 0 or pillar_count >= 4:
        scores["commerce_pro"] = scores.get("commerce_pro", 0.0) + 4.0 + 1.5 * max(pillar_count, commerce_hits)
    elif scores.get("shop", 0) > 0 and (commerce_hits >= 2 or pillar_count >= 3):
        scores["commerce_pro"] = scores.get("commerce_pro", 0.0) + 3.0 * max(commerce_hits, pillar_count - 1)
    elif pillar_count >= 5:
        scores["commerce_pro"] = scores.get("commerce_pro", 0.0) + 2.5 * pillar_count
    elif commerce_hits >= 3 and scores.get("subscriptions", 0) > 0:
        scores["commerce_pro"] = scores.get("commerce_pro", 0.0) + 2.0 * commerce_hits

    # A multi-pillar commerce request must not lose to the raw shop keyword score.
    # The composite signal is deliberately authoritative once catalog/cart/orders/
    # payment pillars are independently present.
    if scores.get("shop", 0.0) > 0 and pillar_count >= 3:
        scores["commerce_pro"] = max(
            scores.get("commerce_pro", 0.0),
            scores["shop"] + 0.25,
        )

    try:
        from .arabic_intent_engine import classify_intent, DOMAIN_TO_PRESET
        for im in classify_intent(request)[:6]:
            preset = DOMAIN_TO_PRESET.get(im.domain)
            if preset:
                scores[preset] = scores.get(preset, 0.0) + float(im.score)
    except Exception:
        pass

    # Modern / security verticals: do not let weak commerce pillars steal the stack
    try:
        from .domain_detector import detect as _dom_detect
        doms = set(_dom_detect(request))
        if "cybersecurity" in doms:
            sec = scores.get("security_ops", 0.0)
            if sec > 0:
                scores["security_ops"] = sec + 6.0
            if scores.get("commerce_pro", 0):
                scores["commerce_pro"] = max(0.0, scores["commerce_pro"] - 5.0)
        # Boost explicit modern presets when domain detector fired
        for domain, preset in (
            ("iot", "iot"),
            ("blockchain", "blockchain"),
            ("ai_ml", "ai_assist"),
            ("devops", "devops"),
            ("gaming", "gaming"),
            ("healthcare", "clinic"),
        ):
            if domain in doms:
                scores[preset] = scores.get(preset, 0.0) + 5.0
                if scores.get("commerce_pro", 0) and domain != "ecommerce":
                    scores["commerce_pro"] = max(0.0, scores["commerce_pro"] - 4.0)
                if scores.get("saas", 0) and domain in {"iot", "ai_ml", "gaming"}:
                    scores["saas"] = max(0.0, scores["saas"] - 3.0)
    except Exception:
        pass

    # Layer-1 Language Understanding soft boost (synonyms / fuzzy / entities)
    try:
        from .language_understanding import understand as _lu
        from .language_understanding import DOMAIN_TO_PRESET as _LU_MAP
        _res = _lu(request or "")
        for d in (_res.domains or [])[:6]:
            preset = _LU_MAP.get(d.domain)
            if preset:
                scores[preset] = scores.get(preset, 0.0) + float(d.score) * 0.85
        if _res.entities.wants_delivery or _res.entities.payment_methods:
            scores["shop"] = scores.get("shop", 0.0) + 1.5
            if any(
                p in (_res.entities.payment_methods or [])
                for p in ("visa", "telegram_payments", "vodafone_cash")
            ):
                scores["shop"] = scores.get("shop", 0.0) + 1.0
    except Exception:
        pass

    # Apply the composite decision after every domain/LU boost so a later raw
    # shop score cannot undo an already proven multi-pillar commerce request.
    if scores.get("shop", 0.0) > 0 and pillar_count >= 3:
        scores["commerce_pro"] = max(
            scores.get("commerce_pro", 0.0),
            scores["shop"] + 0.25,
        )

    # ── Phase B root: exclusive intent families + domain veto ─────────
    scores = _apply_exclusive_intent_locks(scores, request)

    ranked = sorted(
        ((n, s) for n, s in scores.items() if s > 0),
        key=lambda x: (-x[1], x[0]),
    )
    return ranked


def detect_preset(request: str) -> str | None:
    """Return best preset id or None (uses ranked multi-intent scoring)."""
    if _is_minimal_command_bot_request(request):
        return "echo_basic"
    ranked = score_presets(request)
    if not ranked:
        return None
    return ranked[0][0]


def _request_signals(request: str) -> dict[str, float]:
    """Fine-grained intent signals for conflict resolution (not just pack scores)."""
    t = _norm(request)
    def n(keys: Iterable[str]) -> float:
        return float(sum(1 for k in keys if _token_hit(t, k)))

    return {
        "vendor": n(("vendor", "vendors", "بائع", "بائعين", "multi-vendor", "متعدد البائعين", "storefront")),
        "escrow": n(("escrow", "ضمان", "ضمانة")),
        "cart": n(("سلة", "cart", "checkout", "إتمام شراء")),
        "catalog": n(("كتالوج", "catalog", "متجر", "shop", "منتجات")),
        "fleet": n(("أسطول", "fleet", "مندوب", "courier", "مستودع", "warehouse", "hub")),
        "track_only": n(("تتبع", "track", "tracking", "شحنة")),
        "ledger": n(("ledger", "دفتر", "محاسبة", "accounting", "kyc", "aml", "خزينة", "treasury")),
        "wallet_only": n(("محفظة", "wallet", "شحن رصيد", "topup", "top-up")),
        "seats": n(("مقعد", "seats", "seat", "tenant", "workspace", "rbac", "sso", "quota")),
        "trial": n(("trial", "تجربة مجانية", "تجربة")),
        "commerce_explicit": n((
            "commerce pro", "متجر متكامل", "متجر احترافي", "متجر كامل", "متجر شامل",
            "full ecommerce", "commerce suite", "منصة تجارة", "عالمي متكامل",
            "commerce platform", "all-in-one shop",
        )),
        "commerce_rich": n((
            "كتالوج", "سلة", "كوبون", "فواتير", "مدفوعات", "اشتراك", "نقاط", "محفظة",
            "إحالة", "مسابقة", "تحليلات", "تذكرة", "استرجاع", "تجربة مجانية", "سلاسل",
            "إذاعة", "قاعدة معرفة", "وضع صيانة", "ولاء", "متصدرين",
        )),
        "platform": n(("منصة", "platform", "operating system", "suite", "enterprise", "متكامل", "شامل")),
        "saas_word": n(("saas", "ساس", "b2b")),
        "logistics_word": n(("لوجستيات", "logistics", "last mile", "lastmile", "manifest",
                            "shipment", "shipments", "pod", "warehouse", "مستودع", "شحنة", "شحنات")),
        "finance_word": n(("مالية", "finance", "محاسبة", "accounting")),
        "marketplace_word": n(("marketplace", "سوق", "classified", "سوق إلكتروني")),
    }


