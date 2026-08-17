def _load_preset_data() -> dict[str, object]:
    """Load keyword/caps catalogs from JSON (data lives outside this module).

    Search order prefers non-gitignored package paths so the catalog survives
    normal checkouts. Root ``/data`` remains a supported override for local ops.
    """
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "data" / "preset_keywords.json",          # telegram_bot_engine/data/
        here.parents[2] / "data" / "preset_keywords.json",          # repo root /data/ (may be gitignored)
        here.with_name("preset_keywords.json"),                     # beside this module
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                value = json.loads(candidate.read_text(encoding="utf-8"))
                if isinstance(value, dict) and value:
                    return value
        except (OSError, ValueError, TypeError):
            continue
    return {}


_PRESET_DATA = _load_preset_data()


def _pack_from_prefixes(
    prefixes: tuple[str, ...],
    *,
    limit: int = 64,
    extra: tuple[str, ...] = (),
) -> tuple[str, ...]:
    """Real registry keys for a domain (prefix_action) — not phantom labels."""
    from .registry import CAPABILITIES

    out: list[str] = ["start", "help"]
    for e in extra:
        if e in CAPABILITIES or e in {"start", "help", "lang"}:
            out.append(e)
    prefer = (
        "list", "view", "create", "search", "status", "stats", "track", "history",
        "approve", "assign", "checkout", "buy", "sell", "ship", "deliver", "pay",
        "transfer", "refund", "subscribe", "renew", "upgrade", "start_trial",
        "dashboard", "balance", "invoice", "payout", "bid", "catalog",
    )
    for action in prefer:
        for pref in prefixes:
            key = f"{pref}_{action}"
            if key in CAPABILITIES and key not in out:
                out.append(key)
                if len(out) >= limit:
                    return tuple(dict.fromkeys(out))
    for pref in prefixes:
        for key in CAPABILITIES:
            if key.startswith(pref + "_") and key not in out:
                out.append(key)
                if len(out) >= limit:
                    return tuple(dict.fromkeys(out))
    out.append("lang")
    return tuple(dict.fromkeys(out))



def _request_intensity(request: str, presets: list[str] | None = None) -> str:
    """simple | medium | complex — drives pack size caps."""
    presets = list(presets or [])
    t = _norm(request or "")
    complex_domains = {"saas", "marketplace", "logistics", "finance", "commerce_pro"}
    n_complex = sum(1 for d in presets if d in complex_domains)
    enterprise = any(
        k in t
        for k in (
            "enterprise", "all-in-one", "all in one", "منصة", "suite", "operating system",
            "متكامل", "شامل", "ضخم", "multi-tenant", "multi vendor", "multi-vendor",
            "globally", "production grade", "6 month", "شهر", "platform",
        )
    )
    rich = len(t) > 180 or t.count(",") + t.count("،") >= 4 or t.count("+") >= 2
    if n_complex >= 2 or (enterprise and n_complex >= 1) or (enterprise and rich):
        return "complex"
    if n_complex == 1 or any(
        d in presets
        for d in ("shop", "crm", "education", "wallet", "subscriptions", "growth", "creator")
    ):
        # single domain / shop-scale → medium unless ultra-short simple phrase
        if len(t) < 28 and n_complex == 0:
            return "simple"
        return "medium"
    return "simple"


def _pack_limit_for(intensity: str, *, primary: bool) -> int:
    if intensity == "complex":
        return 72 if primary else 48
    if intensity == "medium":
        return 28 if primary else 12
    return 8 if primary else 0


# keyword packs (Arabic + English), lowercase match
_GROUP_KEYS = tuple(_PRESET_DATA.get("_GROUP_KEYS", ()))
_TASK_KEYS = tuple(_PRESET_DATA.get("_TASK_KEYS", ()))
_SUPPORT_KEYS = tuple(_PRESET_DATA.get("_SUPPORT_KEYS", ()))
_NOTES_KEYS = tuple(_PRESET_DATA.get("_NOTES_KEYS", ()))
_SHOP_KEYS = tuple(_PRESET_DATA.get("_SHOP_KEYS", ()))
_SUB_KEYS = tuple(_PRESET_DATA.get("_SUB_KEYS", ()))
_POINTS_KEYS = tuple(_PRESET_DATA.get("_POINTS_KEYS", ()))
_CONTEST_KEYS = tuple(_PRESET_DATA.get("_CONTEST_KEYS", ()))
_I18N_KEYS = tuple(_PRESET_DATA.get("_I18N_KEYS", ()))
_BOOK_KEYS = tuple(_PRESET_DATA.get("_BOOK_KEYS", ()))
_HR_KEYS = tuple(_PRESET_DATA.get("_HR_KEYS", ()))
_SECURITY_KEYS = tuple(_PRESET_DATA.get("_SECURITY_KEYS", ()))

_GROUP_CAPS = tuple(_PRESET_DATA.get("_GROUP_CAPS", ()))
_TASK_CAPS = tuple(_PRESET_DATA.get("_TASK_CAPS", ()))
_SUPPORT_CAPS = tuple(_PRESET_DATA.get("_SUPPORT_CAPS", ()))
_NOTES_CAPS = tuple(_PRESET_DATA.get("_NOTES_CAPS", ()))
_SECURITY_CAPS = tuple(_PRESET_DATA.get("_SECURITY_CAPS", ()))
_SHOP_CAPS = tuple(_PRESET_DATA.get("_SHOP_CAPS", ()))
_SUB_CAPS = tuple(_PRESET_DATA.get("_SUB_CAPS", ()))
_POINTS_CAPS = tuple(_PRESET_DATA.get("_POINTS_CAPS", ()))
_CONTEST_CAPS = tuple(_PRESET_DATA.get("_CONTEST_CAPS", ()))
_GROWTH_CAPS = tuple(_PRESET_DATA.get("_GROWTH_CAPS", ()))
_CRM_CAPS = tuple(_PRESET_DATA.get("_CRM_CAPS", ()))
_SUPPORT_PRO_CAPS = tuple(_PRESET_DATA.get("_SUPPORT_PRO_CAPS", ()))
_EDU_CAPS = tuple(_PRESET_DATA.get("_EDU_CAPS", ()))
_RESTAURANT_CAPS = tuple(_PRESET_DATA.get("_RESTAURANT_CAPS", ()))
_JOBS_CAPS = tuple(_PRESET_DATA.get("_JOBS_CAPS", ()))
_MARKETPLACE_CAPS = tuple(_PRESET_DATA.get("_MARKETPLACE_CAPS", ()))
_SAAS_CAPS = tuple(_PRESET_DATA.get("_SAAS_CAPS", ()))


