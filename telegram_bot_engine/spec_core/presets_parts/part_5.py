def _is_minimal_command_bot_request(request: str) -> bool:
    """True when user only asks for a basic start/help/about bot (no vertical)."""
    t = _norm(request or "")
    if not t:
        return False
    vertical = (
        "متجر", "shop", "store", "ecommerce", "سلة", "cart", "طلب", "طلبات",
        "محفظة", "wallet", "دفع", "payment", "اشتراك", "subscription",
        "نقاط", "points", "تذكرة", "تذاكر", "support", "ticket",
        "مهام", "tasks", "ملاحظات", "notes", "مجموعة", "group", "حظر", "كتم",
        "حجز", "booking", "عيادة", "مطعم", "توصيل", "delivery", "saas",
        "marketplace", "لوجست", "finance", "محاسبة",
    )
    if any(v in t for v in vertical):
        return False
    basic = (
        "/start", "start", "ترحيب", "/help", "help", "مساعدة",
        "/about", "about", "اوامر", "أوامر", "بوت بسيط", "بوت تيليجرام",
        "telegram bot", "simple bot", "basic bot",
    )
    return any(b in t for b in basic)



def sanitize_spec_for_request(spec: "BotSpec", request: str) -> "BotSpec":
    """Remove cross-domain bleed + junk features; ensure core intents are complete."""
    req_n = _norm(request or "")
    if not req_n or spec is None:
        return spec

    from .schema import Feature, Trigger, Action, Messages

    def _feat(key: str, cmd: str | None = None) -> Feature:
        c = cmd or key.replace("task_", "").replace("note_", "").replace("ticket_", "")
        return Feature(
            id=key,
            feature=key,
            trigger=Trigger("command", c),
            action=Action("core", key),
            messages=Messages(),
        )

    # Global junk — never ship unless user explicitly asked
    JUNK = {
        "explicit_command",
        "deep_link_start",
        "smart_help",
        "form_start",
    }
    explicit_junk_ask = any(
        k in req_n for k in ("deep link", "ديپ لينك", "نموذج", "form start", "smart help")
    )

    # _norm folds ة→ه so match both forms for Arabic nouns
    taskish = any(k in req_n for k in ("مهام", "مهمه", "مهمة", "task", "todo", "to-do"))
    notesish = any(k in req_n for k in ("ملاحظات", "ملاحظه", "ملاحظة", "notes", "note "))
    supportish = any(
        k in req_n
        for k in ("دعم", "تذكرة", "تذاكره", "تذاكر", "تذاكيري", "support", "ticket", "mytickets")
    )
    shopish = any(
        k in req_n
        for k in ("متجر", "سلة", "سله", "كتالوج", "shop", "store", "cart", "catalog")
    )
    restaurantish = any(
        k in req_n
        for k in ("مطعم", "طاولة", "طاوله", "حجز طاولة", "restaurant", "طلبات المطعم")
    )

    feats = list(getattr(spec, "features", None) or [])
    keep: list = []
    for f in feats:
        key = str(getattr(f, "feature", "") or "")
        trig = str(getattr(getattr(f, "trigger", None), "id", "") or "")
        # Drop junk capabilities
        if key in JUNK and not explicit_junk_ask:
            continue
        if trig in {"explicitcommand", "deeplinkstart", "smarthelp"} and not explicit_junk_ask:
            continue
        # Tasks primary: drop restaurant/menu bleed
        if taskish and not restaurantish:
            if key.startswith(("menu_", "table_", "order_")) or key in {
                "menu_order", "menu_view", "table_book", "order_status",
            }:
                continue
        # Notes primary (without tasks keywords): drop task_* bleed
        if notesish and not taskish:
            if key.startswith("task_"):
                continue
        # Tasks primary without notes keywords: drop note_* bleed
        if taskish and not notesish:
            if key.startswith("note_"):
                continue
        keep.append(f)

    have = {str(getattr(f, "feature", "")) for f in keep}

    def _ensure(keys: list[str]) -> None:
        nonlocal keep, have
        for k in keys:
            if k not in have:
                cmd = {
                    "task_add": "add",
                    "task_list": "list",
                    "task_done": "done",
                    "task_delete": "delete",
                    "task_clear": "clear",
                    "note_add": "note",
                    "note_list": "notes",
                    "note_delete": "delnote",
                    "ticket_open": "ticket",
                    "ticket_my": "mytickets",
                    "shop_catalog": "shop",
                    "cart_view": "cart",
                    "cart_add": "cartadd",
                    "start": "start",
                    "help": "help",
                    "about": "about",
                }.get(k, k.replace("_", ""))
                keep.append(_feat(k, cmd))
                have.add(k)

    _ensure(["start", "help"])

    if taskish:
        _ensure(["task_add", "task_list"])
        if any(k in req_n for k in ("حذف", "delete", "مسح")):
            _ensure(["task_delete", "task_clear"])
        if any(k in req_n for k in ("تم", "done", "إنهاء", "انهاء")):
            _ensure(["task_done"])
        if getattr(spec, "bot", None) is not None:
            if not getattr(spec.bot, "name", None) or spec.bot.name in {
                "market_bot", "custom_bot", "my_bot", "basic_bot"
            }:
                spec.bot.name = "tasks_bot"

    if notesish:
        _ensure(["note_add", "note_list"])
        if getattr(spec, "bot", None) is not None and not taskish:
            if not getattr(spec.bot, "name", None) or spec.bot.name in {
                "market_bot", "custom_bot", "my_bot", "basic_bot"
            }:
                spec.bot.name = "notes_bot"

    if supportish:
        _ensure(["ticket_open", "ticket_my"])
        if getattr(spec, "bot", None) is not None and not shopish:
            if not getattr(spec.bot, "name", None) or spec.bot.name in {
                "market_bot", "custom_bot", "my_bot", "basic_bot"
            }:
                spec.bot.name = "support_bot"

    if shopish:
        _ensure(["shop_catalog"])
        if any(k in req_n for k in ("سلة", "سله", "cart", "اضافه للسله", "إضافة للسلة")):
            _ensure(["cart_view", "cart_add"])
        if getattr(spec, "bot", None) is not None:
            if not getattr(spec.bot, "name", None) or spec.bot.name in {
                "custom_bot", "my_bot", "basic_bot"
            }:
                spec.bot.name = "shop_bot"

    # about when asked
    if any(k in req_n for k in ("/about", "about", "عن البوت", "حول")):
        _ensure(["about"])

    # Support phrasing: تذاكري / my tickets
    if supportish and any(k in req_n for k in ("تذاكري", "تذاكره", "mytickets", "my tickets", "تذاكري")):
        _ensure(["ticket_my"])

    # Dedup by feature key (keep first)
    seen: set[str] = set()
    deduped = []
    for f in keep:
        key = str(getattr(f, "feature", "") or "")
        if key in seen:
            continue
        seen.add(key)
        deduped.append(f)
    spec.features = deduped
    return spec

def default_spec_from_request(request: str, *, user_id: int = 0) -> BotSpec:
    """Always-on high-quality pack when the user asks for a bot.

    Uses multi-intent scoring, dynamic capability extraction, and multi-domain
    composition when several domains match.
    """
    # Minimal start/help/about requests must NOT expand into commerce_pro packs.
    if _is_minimal_command_bot_request(request):
        s = session_for_preset("echo_basic", user_id=user_id, bot_name="basic_bot")
        # Optional /about when explicitly mentioned
        rt = _norm(request or "")
        if any(x in rt for x in ("/about", "about", "عن البوت", "حول")):
            try:
                s.selected.add("about")
            except Exception:
                pass
        if any(x in rt for x in ("/lang", "lang", "لغة", "اللغة")) and "عربي وانجليزي" in rt:
            try:
                s.selected.add("lang")
            except Exception:
                pass
        return s.to_spec()

    # Dynamic composer handles cybersecurity / multi-domain extraction first
    try:
        from .domain_detector import detect as _detect_domains
        from .dynamic_composer import compose_from_text

        domains = _detect_domains(request)
        modern = {
            "cybersecurity", "iot", "blockchain", "ai_ml", "devops",
            "healthcare", "gaming", "education", "marketplace",
        }
        # Prefer dynamic path for modern verticals / multi-domain requests
        if (modern & set(domains)) or len(domains) >= 2:
            return compose_from_text(request, user_id=user_id)
    except Exception:
        pass

    stack = detect_preset_stack(request, limit=4)
    if not stack:
        # Intent engine (Arabic synonyms) before any hardcoded fallback
        try:
            from .arabic_intent_engine import smart_detect_preset, is_clearly_non_bot
            if is_clearly_non_bot(request):
                stack = ["echo_basic"]
            else:
                sp = smart_detect_preset(request)
                stack = [sp] if sp else ["echo_basic"]
        except Exception:
            stack = ["echo_basic"]
    s = compose_session(stack, user_id=user_id, request=request)

    # Always enrich with extracted real keys (safe no-op if extractor fails)
    try:
        from .capability_extractor import extract_all
        from .domain_detector import detect as _detect_domains

        for key in extract_all(request, _detect_domains(request)):
            from .registry import CAPABILITIES as _CAPS
            if key in _CAPS:
                s.selected.add(key)
    except Exception:
        pass

    # Layer-2 Intent Analysis: multi-intent plan grounded in Layer-1 LU
    try:
        from .language_understanding import analyze_intent as _analyze_intent
        from .language_understanding import understand as _lu_understand
        from .registry import CAPABILITIES as _CAPS

        if lu is None:
            lu = _lu_understand(request or "")
        intent = _analyze_intent(request or "", lu=lu)

        # Feature plan from intent engine (already filtered against bleed)
        for key in (intent.feature_plan or []):
            if key in _CAPS:
                s.selected.add(key)

        # Prefer intent preset when stack is thin/generic
        if intent.preset and (not stack or stack[0] in {"shop", "custom", "group_admin"}):
            if intent.preset not in (stack or []):
                stack = [intent.preset] + list(stack or [])
        for sp in (intent.secondary_presets or [])[:3]:
            if sp not in (stack or []):
                stack = list(stack or []) + [sp]

        # Stamp description with intent decision (debug + differentiation)
        bits = []
        if intent.primary:
            bits.append(
                f"intent={intent.primary.intent}:{intent.primary.confidence:.2f}"
            )
        if intent.secondary:
            bits.append(
                "sec=" + ",".join(f"{x.intent}:{x.weight:.2f}" for x in intent.secondary[:3])
            )
        bits.append(f"skill={intent.skill_level}")
        bits.append(f"complexity={intent.complexity}")
        bits.append(f"lang={intent.language}")
        if intent.should_ask:
            bits.append("ask=" + (intent.ask_reason or "yes"))
        if lu and lu.entities.product:
            bits.append(f"product={lu.entities.product}")
        if lu and getattr(lu.entities, "security_checks", None):
            bits.append("sec_checks=" + ",".join(lu.entities.security_checks[:4]))
        if bits:
            base = (s.description or "").strip()
            s.set_description((base + " | " if base else "") + "L2: " + "; ".join(bits))

        # Attach questions onto description tip for upstream UX (non-breaking)
        if intent.should_ask and intent.questions:
            tip = " | ask: " + " / ".join(intent.questions[:2])
            s.set_description((s.description or "") + tip)
        try:
            from .language_understanding import suggest as _suggest
            rep = _suggest(request or "", intent=intent, lu=lu, selected_features=list(s.selected) if hasattr(s, "selected") else None)
            top = [x.feature for x in (rep.build or [])[:3]]
            if top:
                s.set_description((s.description or "") + " | suggest: " + ",".join(top))
        except Exception:
            pass
    except Exception:
        pass

    # Disambiguate Arabic "قائمة" (list vs restaurant menu) when tasks are primary
    try:
        req_n = _norm(request or "")
        taskish = any(k in req_n for k in ("مهام", "مهمة", "task", "todo", "to-do"))
        restaurantish = any(
            k in req_n
            for k in ("مطعم", "طاولة", "حجز طاولة", "restaurant", "menu order", "طلبات المطعم")
        )
        if taskish and not restaurantish and hasattr(s, "selected"):
            drop = {
                k
                for k in list(s.selected)
                if str(k).startswith(
                    ("menu_", "table_", "order_", "restaurant", "form_")
                )
                or str(k) in {
                    "menu_order", "menu_view", "table_book", "order_status",
                    "form_start", "deep_link_start", "smart_help",
                }
            }
            s.selected -= drop
            s.selected.update({"start", "help", "task_add", "task_list"})
    except Exception:
        pass

    if not s.bot_name or s.bot_name in {"group_admin_bot", "custom_bot", "my_bot", "market_bot"}:
        # Prefer intent-based name
        req_n = _norm(request or "")
        if any(k in req_n for k in ("مهام", "مهمة", "task")):
            s.set_name("tasks_bot")
        elif any(k in req_n for k in ("جروب", "مجموعة", "حظر", "كتم", "مشرف", "pubg", "ببجي", "group admin")):
            s.set_name("group_admin_bot")
        elif any(k in req_n for k in ("متجر", "shop", "store")):
            s.set_name("market_bot")
        else:
            s.set_name("basic_bot")
    return s.to_spec()


def session_for_preset(preset: str, *, user_id: int = 0, bot_name: str = "") -> BuilderSession:
    s = BuilderSession(user_id=user_id)
    if preset == "group_management":
        s.set_name(bot_name or "group_admin_bot")
        s.set_description("بوت إدارة مجموعات: حظر/كتم/طرد/ترحيب/قوانين")
        for k in _GROUP_CAPS:
            s.selected.add(k)
    elif preset == "support_tickets":
        s.set_name(bot_name or "support_bot")
        s.set_description("بوت تذاكر دعم")
        for k in _SUPPORT_CAPS:
            s.selected.add(k)
    elif preset == "tasks":
        s.set_name(bot_name or "tasks_bot")
        s.set_description("بوت مهام شخصية")
        for k in _TASK_CAPS:
            s.selected.add(k)
    elif preset == "notes":
        s.set_name(bot_name or "notes_bot")
        s.set_description("بوت ملاحظات")
        for k in _NOTES_CAPS:
            s.selected.add(k)
    elif preset == "security_ops":
        s.set_name(bot_name or "security_ops_bot")
        s.set_description(
            "Cybersecurity ops: domain checks (DNS/TLS/HTTP/headers), "
            "incident reports, projects, reports, audit notes"
        )
        for k in _SECURITY_CAPS:
            s.selected.add(k)
    elif preset == "shop":
        s.set_name(bot_name or "shop_bot")
        s.set_description(
            "Global shop bot with Telegram Payments invoices, catalog, orders, and /lang (en/ar)"
        )
        for k in _SHOP_CAPS:
            s.selected.add(k)
    elif preset == "subscriptions":
        s.set_name(bot_name or "subscription_bot")
        s.set_description(
            "Subscription bot for end-users: plans, subscribe, my_sub, admin grant/revoke, i18n"
        )
        for k in _SUB_CAPS:
            s.selected.add(k)
    elif preset == "points":
        s.set_name(bot_name or "points_bot")
        s.set_description(
            "Loyalty/points bot: balance, leaderboard, admin grant_points, i18n"
        )
        for k in _POINTS_CAPS:
            s.selected.add(k)
    elif preset == "contests":
        s.set_name(bot_name or "contest_bot")
        s.set_description(
            "Contests/giveaways bot: join, entries, admin create/end/draw, i18n"
        )
        for k in _CONTEST_CAPS:
            s.selected.add(k)
    elif preset == "growth":
        s.set_name(bot_name or "growth_bot")
        s.set_description("Referral, daily check-in, streaks, achievements — growth engine for end-users")
        for k in _GROWTH_CAPS:
            s.selected.add(k)
    elif preset == "crm":
        s.set_name(bot_name or "crm_bot")
        s.set_description("Sales CRM: leads, pipeline, deals, follow-ups")
        for k in _CRM_CAPS:
            s.selected.add(k)
    elif preset == "support_pro":
        s.set_name(bot_name or "support_pro_bot")
        s.set_description("Pro support: tickets, priority, assign, knowledge base, CSAT")
        for k in _SUPPORT_PRO_CAPS:
            s.selected.add(k)
    elif preset == "education":
        s.set_name(bot_name or "education_bot")
        s.set_description("Courses, lessons, quizzes, homework, certificates")
        for k in _EDU_CAPS:
            s.selected.add(k)
    elif preset == "restaurant":
        s.set_name(bot_name or "restaurant_bot")
        s.set_description("Restaurant menu, orders, table booking")
        for k in _RESTAURANT_CAPS:
            s.selected.add(k)
    elif preset == "jobs":
        s.set_name(bot_name or "jobs_bot")
        s.set_description("Job board: list, apply, post (admin)")
        for k in _JOBS_CAPS:
            s.selected.add(k)
    elif preset == "marketplace":
        s.set_name(bot_name or "marketplace_bot")
        s.set_description("Marketplace: vendors, listings, escrow, bids, payouts, disputes")
        s.selected.update(_marketplace_pack(limit=28))
    elif preset == "saas":
        s.set_name(bot_name or "saas_bot")
        s.set_description("SaaS: seats, trials, quotas, billing, RBAC, webhooks, flags")
        s.selected.update(_saas_pack(limit=28))
    elif preset == "logistics":
        s.set_name(bot_name or "logistics_bot")
        s.set_description("Logistics: shipments, fleet, routes, hubs, POD, last-mile")
        s.selected.update(_logistics_pack(limit=28))
    elif preset == "finance":
        s.set_name(bot_name or "finance_bot")
        s.set_description("Light finance: ledger, payouts, KYC, invoices, wallets")
        s.selected.update(_finance_pack(limit=28))
    elif preset == "community":
        s.set_name(bot_name or "community_bot")
        s.set_description("Community feed, profiles, posts, moderation queue")
        for k in _COMMUNITY_CAPS:
            s.selected.add(k)
    elif preset == "events":
        s.set_name(bot_name or "events_bot")
        s.set_description("Events and RSVP management")
        for k in _EVENTS_CAPS:
            s.selected.add(k)
    elif preset == "wallet":
        s.set_name(bot_name or "wallet_bot")
        s.set_description("User wallet: balance, top-up, transfer, history")
        for k in _WALLET_CAPS:
            s.selected.add(k)
    elif preset == "creator":
        s.set_name(bot_name or "creator_bot")
        s.set_description(
            "Creator monetization: paid content, tips, membership, referrals, global i18n"
        )
        for k in _CREATOR_CAPS:
            s.selected.add(k)
    elif preset == "commerce_pro":
        s.set_name(bot_name or "commerce_pro_bot")
        s.set_description(
            "Full commerce suite: shop+cart+payments+subs+points+wallet+growth+analytics"
        )
        for k in _COMMERCE_PRO_CAPS:
            s.selected.add(k)
        # Keep session language (default ar); callers may set en for global EN packs

    elif preset == "fitness":
        s.set_name(bot_name or "fitness_bot")
        s.set_description("Gym/fitness: schedule, book session, membership, check-in")
        for k in _FITNESS_CAPS:
            s.selected.add(k)
    elif preset == "realestate":
        s.set_name(bot_name or "realestate_bot")
        s.set_description("Real estate listings, search, inquiries")
        for k in _REALESTATE_CAPS:
            s.selected.add(k)
    elif preset == "clinic":
        s.set_name(bot_name or "clinic_bot")
        s.set_description("Clinic appointments: slots, book, cancel")
        for k in _CLINIC_CAPS:
            s.selected.add(k)
    elif preset == "auction":
        s.set_name(bot_name or "auction_bot")
        s.set_description("Auctions: list, bid, create, my bids")
        for k in _AUCTION_CAPS:
            s.selected.add(k)
    elif preset == "delivery":
        s.set_name(bot_name or "delivery_bot")
        s.set_description("Delivery tracking and shipment status")
        for k in _DELIVERY_CAPS:
            s.selected.add(k)
    elif preset == "booking":
        s.set_name(bot_name or "booking_bot")
        s.set_description("بوت حجوزات")
        for k in ("start", "help", "book_slot", "book_list", "book_cancel", "book_admin_list"):
            s.selected.add(k)
    elif preset == "hr":
        s.set_name(bot_name or "hr_bot")
        s.set_description("بوت موارد بشرية مبسط")
        for k in ("start", "help", "hr_leave_request", "hr_leave_list", "hr_checkin"):
            s.selected.add(k)
    elif preset == "iot":
        s.set_name(bot_name or "iot_bot")
        s.set_description("IoT ops: devices, sensors, notes, tasks (sqlite registry)")
        for k in _IOT_CAPS:
            s.selected.add(k)
    elif preset == "blockchain":
        s.set_name(bot_name or "blockchain_bot")
        s.set_description("Crypto wallet ops: balance, history, transfer (no chain RPC required)")
        for k in _BLOCKCHAIN_CAPS:
            s.selected.add(k)
    elif preset == "ai_assist":
        s.set_name(bot_name or "ai_assist_bot")
        s.set_description("AI workspace: notes, tasks, projects (prompts logged locally)")
        for k in _AI_CAPS:
            s.selected.add(k)
    elif preset == "devops":
        s.set_name(bot_name or "devops_bot")
        s.set_description("DevOps ops: deploys, envs, secrets, logs, tasks")
        for k in _DEVOPS_CAPS:
            s.selected.add(k)
    elif preset == "gaming":
        s.set_name(bot_name or "gaming_bot")
        s.set_description("Gaming: leaderboard, contests, achievements, points")
        for k in _GAMING_CAPS:
            s.selected.add(k)
    elif preset in {"echo_basic", "basic", "generic", "echo"}:
        s.set_name(bot_name or "basic_bot")
        s.set_description("بوت أساسي: /start و /help")
        s.selected.update({"start", "help"})
    else:
        s.set_name(bot_name or "custom_bot")
        s.selected.update({"start", "help"})
    return s


