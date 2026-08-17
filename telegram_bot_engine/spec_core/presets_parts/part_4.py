def prioritize_preset_stack(
    ranked: list[tuple[str, float]],
    request: str,
    *,
    limit: int = 6,
) -> list[str]:
    """Terrifyingly smart merge priority for overlapping domains.

    Rules (highest impact first):
    1) Explicit commerce_pro phrase wins pure shop-suite primary.
    2) Marketplace beats shop when vendor/escrow/multi-vendor signals exist.
    3) Logistics beats thin delivery when fleet/warehouse/route signals exist.
    4) Finance beats wallet when ledger/KYC/accounting signals exist.
    5) SaaS beats bare subscriptions when seats/trial/tenant/RBAC signals exist.
    6) Never inject commerce_pro into pure SaaS / pure logistics / pure finance.
    7) Secondary domains keep order by *adjusted* score, not raw keyword count only.
    """
    if not ranked:
        return []

    sig = _request_signals(request)
    scores = {n: float(s) for n, s in ranked}

    # Commerce Pro override: rich multi-feature Arabic commerce specs
    # win over bare shop even without the exact phrase "commerce pro".
    if sig.get("commerce_explicit", 0) >= 1 or sig.get("commerce_rich", 0) >= 6:
        scores["commerce_pro"] = scores.get("commerce_pro", 0.0) + 8.0 + 0.8 * sig.get("commerce_rich", 0)
        # Demote thin single-domain shop when suite is clearly intended
        if scores.get("shop", 0) > 0:
            scores["shop"] = max(0.1, scores.get("shop", 0) - 4.0)
    elif sig.get("commerce_rich", 0) >= 4 and scores.get("shop", 0) > 0:
        scores["commerce_pro"] = scores.get("commerce_pro", 0.0) + 5.0 + 0.5 * sig.get("commerce_rich", 0)

    # Specificity bonuses / penalties
    if sig["vendor"] or sig["escrow"] or sig["marketplace_word"]:
        scores["marketplace"] = scores.get("marketplace", 0.0) + 4.0 + 1.5 * sig["vendor"] + 2.0 * sig["escrow"]
        scores["shop"] = scores.get("shop", 0.0) - 2.5
        if not sig["commerce_explicit"]:
            scores["commerce_pro"] = scores.get("commerce_pro", 0.0) - 1.5

    if sig["fleet"] or sig["logistics_word"]:
        scores["logistics"] = scores.get("logistics", 0.0) + 4.0 + 1.2 * sig["fleet"]
        scores["delivery"] = scores.get("delivery", 0.0) - 2.0

    if sig["ledger"] or sig["finance_word"]:
        scores["finance"] = scores.get("finance", 0.0) + 4.0 + 1.2 * sig["ledger"]
        scores["wallet"] = scores.get("wallet", 0.0) - 1.5

    if sig["seats"] or sig["trial"] or sig["saas_word"]:
        scores["saas"] = scores.get("saas", 0.0) + 4.0 + 1.2 * sig["seats"] + 1.0 * sig["trial"]
        scores["subscriptions"] = scores.get("subscriptions", 0.0) - 1.2

    if sig["commerce_explicit"]:
        scores["commerce_pro"] = scores.get("commerce_pro", 0.0) + 6.0

    if sig["cart"] and not (sig["vendor"] or sig["escrow"]):
        scores["shop"] = scores.get("shop", 0.0) + 3.5
        # bare shop/cart — do NOT escalate to commerce_pro unless explicit
        if not sig["commerce_explicit"]:
            scores["commerce_pro"] = scores.get("commerce_pro", 0.0) - 3.0

    # Wallet top-up phrasing often contains "شحن" — do not treat as logistics
    # Keep logistics when shipment/POD/track signals exist (6-month potato platforms)
    if (
        sig["wallet_only"]
        and not sig["logistics_word"]
        and not sig["fleet"]
        and not sig.get("track_only")
    ):
        scores["logistics"] = scores.get("logistics", 0.0) - 5.0
        scores["delivery"] = scores.get("delivery", 0.0) - 3.0
        scores["wallet"] = scores.get("wallet", 0.0) + 3.0

    # Platform multi-domain: boost co-mentioned complex systems
    if sig["platform"]:
        for d in ("saas", "marketplace", "logistics", "finance"):
            if scores.get(d, 0) > 0:
                scores[d] += 1.5

    # Order-of-mention: earlier domain keyword in the request wins ties
    tnorm = _norm(request)
    mention_pos: dict[str, int] = {}
    markers = {
        "saas": ("saas", "ساس", "workspace", "مقعد", "seats"),
        "marketplace": ("marketplace", "سوق", "escrow", "multi-vendor", "بائعين"),
        "logistics": ("logistics", "لوجستيات", "أسطول", "fleet", "مستودع"),
        "finance": ("finance", "مالية", "ledger", "محاسبة", "kyc"),
        "commerce_pro": ("commerce pro", "متجر متكامل", "commerce suite"),
        "shop": ("سلة", "cart", "كتالوج", "catalog", "متجر"),
        "wallet": ("محفظة", "wallet"),
    }
    for dom, words in markers.items():
        positions = [tnorm.find(w) for w in words if w in tnorm]
        positions = [x for x in positions if x >= 0]
        if positions:
            mention_pos[dom] = min(positions)
            # slight bonus for appearing early
            scores[dom] = scores.get(dom, 0.0) + max(0.0, 2.0 - (mention_pos[dom] / 40.0))

    # Drop noise domains with non-positive adjusted score
    # Tie-break: higher score, then earlier mention, then name
    def _sort_key(item: tuple[str, float]) -> tuple:
        name, sc = item
        pos = mention_pos.get(name, 10_000)
        return (-sc, pos, name)

    ordered = sorted(scores.items(), key=_sort_key)
    out = [n for n, s in ordered if s > 0]

    primary = out[0] if out else None

    # Conflict pruning
    pure_complex = primary in {"saas", "logistics", "finance", "marketplace"}
    if pure_complex and not sig["commerce_explicit"]:
        # keep commerce_pro only if strong residual shop suite signal without marketplace primary
        if primary != "marketplace":
            out = [x for x in out if x != "commerce_pro"]
        if primary == "marketplace":
            out = [x for x in out if x not in {"shop"}]
        if primary == "logistics":
            out = [x for x in out if x != "delivery"]
        if primary == "finance":
            out = [x for x in out if x != "wallet"] or out
            out = [x for x in out if x != "wallet"]
        if primary == "saas":
            out = [x for x in out if x != "subscriptions"]

    if primary == "shop" and not sig["commerce_explicit"]:
        out = [x for x in out if x != "commerce_pro"]

    if "commerce_pro" in out:
        out = [x for x in out if x not in {"shop", "subscriptions", "points", "growth"} or x == "commerce_pro"]

    # Group moderation primary: only group_management (+ optional welcome/content)
    if primary in {"group_management", "group_admin"}:
        out = [x for x in out if x in {"group_management", "group_admin"}]
        if "group_management" not in out:
            out.insert(0, "group_management")
        return out[: max(1, limit)]

    # Phase B: pure tasks primary must not drag booking/clinic/shop
    if primary == "tasks":
        out = [
            x for x in out
            if x not in {
                "booking", "clinic", "shop", "commerce_pro", "marketplace",
                "restaurant", "hr", "fitness", "auction", "delivery",
            }
        ]
        if "tasks" not in out:
            out.insert(0, "tasks")

    # Protect high-signal complex domains before soft backbone / cap
    complex_domains = ("saas", "marketplace", "logistics", "finance", "commerce_pro")
    hard = [x for x in out if x in complex_domains and scores.get(x, 0) >= 3.0]
    soft = [x for x in out if x not in hard]

    multi_complex = len(hard)
    if multi_complex >= 2 or (sig.get("platform") and multi_complex >= 1):
        for b in ("support_pro", "crm"):
            if b not in soft and b not in hard:
                soft.append(b)
    elif primary in {"group_management", "support_tickets", "tasks"}:
        pass
    else:
        soft = [x for x in soft if x not in {"education", "community", "events"} or scores.get(x, 0) >= 3.0]

    # Hard complex domains first (preserve 6-month potatoes), then soft
    merged = list(dict.fromkeys(hard + soft))
    cap = max(1, min(limit, 8))
    # Never drop a hard domain for backbone if we still have room pressure
    if len(hard) >= cap:
        return hard[:cap]
    return merged[:cap]


def detect_preset_stack(request: str, *, limit: int = 8) -> list[str]:
    """Multi-domain stack — domain decision first, then ranked presets.

    Phase B root: when domain lock says tasks-only, return ``["tasks"]``
    without letting residual booking scores re-enter via prioritization.
    """
    try:
        from .domain_detector import decide as _domain_decide
        dec = _domain_decide(request)
        if dec.primary in {"tasks", "projects"} and dec.confidence >= 0.45:
            return ["tasks"]
        if dec.primary == "group_moderation" and dec.confidence >= 0.45:
            return ["group_management"]
        ranked = score_presets(request)
        ranked = [(n, s) for n, s in ranked if n not in dec.blocked_presets]
        stack = prioritize_preset_stack(ranked, request, limit=limit)
        stack = [p for p in stack if p not in dec.blocked_presets]
        return stack[: max(1, limit)] or (["tasks"] if dec.primary == "tasks" else [])
    except Exception:
        ranked = score_presets(request)
        return prioritize_preset_stack(ranked, request, limit=limit)



def compose_session(
    presets: list[str],
    *,
    user_id: int = 0,
    bot_name: str = "",
    request: str = "",
) -> BuilderSession:
    """Merge multiple preset capability sets into one intelligent session."""
    if not presets:
        return session_for_preset("echo_basic", user_id=user_id, bot_name=bot_name)

    primary = presets[0]
    s = session_for_preset(primary, user_id=user_id, bot_name=bot_name)
    for extra in presets[1:]:
        other = session_for_preset(extra, user_id=user_id)
        s.selected |= other.selected

    # Intensity-aware domain packs: medium bots get a hard ceiling
    names = list(presets)
    primary = names[0] if names else ""
    secondary = set(names[1:])
    intensity = _request_intensity(request, names)

    def _take(pack: tuple[str, ...], n: int) -> list[str]:
        core = ["start", "help", "lang"]
        body = [x for x in pack if x not in core]
        return list(dict.fromkeys(core + body[: max(0, n - len(core))]))

    # Strip prior fat domain keys from session_for_preset so intensity can re-apply
    _dom_prefixes = (
        "saas_", "seat_", "plan3_", "billing2_", "meter_", "quota_", "subscription2_",
        "trial2_", "addon2_", "workspace2_", "org_", "team2_", "rbac_", "flag2_",
        "webhook3_", "apikey_", "oauth2_",
        "mkt_", "listing2_", "vendor2_", "buyer_", "offer2_", "bid2_", "escrow_",
        "payout2_", "commission2_", "catalog2_", "storefront_", "auction3_",
        "rfq2_", "quote2_", "dispute3_", "review3_",
        "logi_", "ship4_", "fleet2_", "route3_", "hub2_", "dock2_", "warehouse4_",
        "courier2_", "manifest_", "lane_", "container_", "lastmile_", "pod2_",
        "eta2_", "load2_", "trip_",
        "fin_", "ledger2_", "journal_", "payout3_", "settle2_", "recon_", "treasury_",
        "fx_", "card3_", "wallet3_", "loan2_", "credit2_", "limit2_", "kyc2_", "aml2_",
        "invoice4_", "receivable_", "payable_", "tax3_", "fee2_",
    )
    if intensity in {"medium", "simple"} and any(
        d in names for d in ("saas", "marketplace", "logistics", "finance")
    ):
        s.selected = {
            x for x in s.selected
            if not any(x.startswith(pref) for pref in _dom_prefixes)
        }

    def _apply_domain(name: str, builder) -> None:
        if name not in names:
            return
        is_primary = primary == name
        lim = _pack_limit_for(intensity, primary=is_primary)
        if lim <= 0:
            return
        s.selected.update(builder(limit=lim))

    _apply_domain("saas", _saas_pack)
    _apply_domain("marketplace", _marketplace_pack)
    _apply_domain("logistics", _logistics_pack)
    _apply_domain("finance", _finance_pack)

    if primary == "commerce_pro":
        if intensity == "complex":
            s.selected.update(_COMMERCE_PRO_CAPS)
        else:
            s.selected.update(_take(_COMMERCE_PRO_CAPS, 36))
    elif "commerce_pro" in secondary:
        s.selected.update(_take(_COMMERCE_PRO_CAPS, 24 if intensity != "complex" else 40))
    elif primary == "shop" or "shop" in secondary:
        s.selected.update(_SHOP_CAPS)

    # Hard ceiling: medium stays lean; complex capped for runtime health
    if intensity == "complex" and len(s.selected) > 72:
        core = {"start", "help", "lang"}
        ordered = [x for x in s.selected if x in core] + [x for x in s.selected if x not in core]
        s.selected = set(list(dict.fromkeys(ordered))[:72])
    if intensity == "medium" and len(s.selected) > 40:
        # Prefer primary domain + core commands
        core = {"start", "help", "lang"}
        primary_prefs = {
            "saas": ("saas_", "seat_", "plan3_", "quota_", "trial2_"),
            "marketplace": ("mkt_", "listing2_", "vendor2_", "escrow_", "payout2_"),
            "logistics": ("logi_", "ship4_", "fleet2_", "pod2_", "warehouse4_"),
            "finance": ("fin_", "ledger2_", "kyc2_", "invoice4_", "wallet3_"),
            "commerce_pro": ("shop_", "cart_", "coupon_", "wallet_", "sub"),
            "shop": ("shop_", "cart_"),
        }.get(primary, ())
        kept = [x for x in s.selected if x in core]
        rest = [x for x in s.selected if x not in core]
        rest_pri = [x for x in rest if any(x.startswith(p) for p in primary_prefs)]
        rest_other = [x for x in rest if x not in rest_pri]
        ordered = list(dict.fromkeys(kept + rest_pri + rest_other))
        s.selected = set(ordered[:40])

    # Primary-aware bot identity (name + description)
    _identity = {
        "saas": ("saas_platform_bot", "SaaS platform: seats, trials, quotas, RBAC, billing"),
        "marketplace": ("marketplace_platform_bot", "Marketplace: vendors, escrow, listings, payouts"),
        "logistics": ("logistics_platform_bot", "Logistics: fleet, warehouses, routes, POD tracking"),
        "finance": ("finance_ops_bot", "Finance ops: ledger, KYC, payouts, invoices"),
        "commerce_pro": ("commerce_pro_bot", "Commerce pro: shop, cart, subs, points, wallet, growth"),
        "shop": ("shop_bot", "Shop: catalog, cart, orders"),
    }
    if not bot_name and primary in _identity:
        nm, desc = _identity[primary]
        s.set_name(nm)
        s.set_description(desc)
    elif primary in _identity and (not s.bot_name or s.bot_name in {
        "group_admin_bot", "custom_bot", "my_bot", "market_bot"
    }):
        nm, desc = _identity[primary]
        s.set_name(nm)
        s.set_description(desc)

    # Intelligence: global / i18n language
    if _has_any(request, _I18N_KEYS):
        s.selected.add("lang")
        if s.language in {"ar", ""}:
            s.language = "en"

    # Name from request tokens if still generic
    if bot_name:
        s.set_name(bot_name)
    elif request:
        token = re.sub(r"[^a-zA-Z0-9_\u0600-\u06FF]+", "_", request.strip())[:32].strip("_")
        if token and s.bot_name in {
            "group_admin_bot", "custom_bot", "my_bot", "market_bot", "shop_bot",
        }:
            s.set_name(f"bot_{token[:20]}" if not token[0].isalpha() else token[:24])

    # Description reflects composition
    if len(presets) > 1:
        s.set_description(
            f"Composed bot: {', '.join(presets)} — multi-intent zero-AI pack"
        )

    t = _norm(request)
    complexity_hit = any(
        k in t for k in (
            "متكامل", "enterprise", "all-in-one", "all in one", "منصة", "suite",
            "ضخم", "احترافي", "production", "operating system", "جاهز للسوق",
            "rule them all", "كل شيء", "شامل",
        )
    )
    multi_complex = sum(
        1 for d in ("saas", "marketplace", "logistics", "finance", "commerce_pro")
        if d in presets
    )
    # Only dump broad backbone when user clearly wants a huge multi-domain platform
    if complexity_hit and multi_complex >= 2:
        for pack in (
            _SUPPORT_PRO_CAPS, _CRM_CAPS, _GROWTH_CAPS, _WALLET_CAPS,
        ):
            s.selected.update(pack)
        s.selected.add("lang")
    elif complexity_hit and multi_complex == 0 and len(presets) >= 3:
        # legacy multi-intent without complex systems — light backbone only
        s.selected.update(_SUPPORT_PRO_CAPS)
        s.selected.add("lang")

    # UI language: Arabic request → Arabic menu/welcome
    if any("\u0600" <= ch <= "\u06FF" for ch in (request or "")):
        s.language = "ar"
    elif any(k in _norm(request) for k in ("english", "global en", "en only")):
        s.language = "en"

    # Phase C root: authoritative capability resolution replaces fat packs
    if request:
        try:
            from .capability_extractor import resolve_capabilities
            resolved = resolve_capabilities(request, presets=list(presets or []))
            if resolved:
                s.selected = set(resolved)
            if "group_management" in (presets or []):
                s.set_name("group_admin_bot")
                s.set_description("بوت إدارة جروبات: حظر/كتم/طرد/تحذير/ترحيب/حماية")
        except Exception:
            pass

    return s


def is_bot_request(request: str) -> bool:
    t = _norm(request)
    keys = (
        "بوت", "bot", "telegram", "تيليجرام", "تليجرام", "tg ",
        "اعمل", "أنشئ", "انشئ", "سوي", "أبغى", "ابي", "أريد", "عايز", "عاوز",
        "create", "make", "build",
    )
    return any(k in t for k in keys)


# Full marketplace-grade default pack: group admin + welcome + tickets + basics
_DEFAULT_CAPS = tuple(dict.fromkeys(
    list(_GROUP_CAPS) + list(_SUPPORT_CAPS) + ["ping", "about"]
))



