"""Acceptance gate for generated BotSpec quality (Phase E root).

Single checkpoint before codegen. Responsibilities:
1. Strip cross-vertical capability leaks (clinic on tasks, clinic on shop, …).
2. Ensure required lean caps exist for the primary domain (repair inject).
3. Fix misleading bot names / descriptions.
4. Report ok/errors/warnings for observability.

All production generation paths that build a BotSpec should call ``accept_spec``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from .domain_detector import DomainDecision, decide


@dataclass
class GateResult:
    ok: bool
    stripped: list[str] = field(default_factory=list)
    injected: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    decision_primary: str | None = None
    feature_ids_after: list[str] = field(default_factory=list)


_TASKS_DENY_PREFIXES = (
    "clinic_", "shop_", "cart_", "book_", "wallet_", "mkt_", "saas_",
    "ticket_", "patient_", "prescription_", "doctor",
)
_TASKS_DENY_EXACT = frozenset(
    {
        "book_slot", "book_list", "book_cancel", "book_admin_list",
        "ticket_open", "ticket_list", "ticket_status", "ticket_my",
        "shop_catalog", "cart_view", "shop_buy", "shop_orders", "shop_my_orders",
        "shop_add_item",
    }
)
_TASKS_REQUIRE = ("task_add", "task_list")
_TASKS_OPTIONAL_LEAN = (
    "task_delete", "task_done", "task_clear", "remind_set", "remind_list",
    "start", "help", "lang",
)

_SHOP_DENY_PREFIXES = ("clinic_", "patient_", "prescription_")
_SHOP_DENY_EXACT = frozenset({"clinic_book", "clinic_my", "clinic_cancel", "clinic_slots"})

_CLINIC_DENY_PREFIXES = ("shop_", "cart_", "mkt_")
_CLINIC_DENY_EXACT = frozenset(
    {"shop_catalog", "cart_view", "shop_buy", "shop_orders", "wallet_topup"}
)


def _fid(f: Any) -> str:
    return str(getattr(f, "feature", None) or getattr(f, "id", None) or "")


def _feature_ids(spec: Any) -> list[str]:
    out: list[str] = []
    for f in getattr(spec, "features", None) or []:
        fid = _fid(f)
        if fid:
            out.append(fid)
    return out


def _append_feature(spec: Any, key: str) -> bool:
    """Inject a minimal Feature for *key* from the registry. Returns True if added."""
    try:
        from .registry import get_capability
        from .schema import Feature, Trigger, Action, Messages
        from .builder import DEFAULT_COMMANDS, DEFAULT_SUCCESS_AR
    except Exception:
        return False
    cap = get_capability(key)
    if not cap:
        return False
    existing = set(_feature_ids(spec))
    if key in existing:
        return False
    cmd = DEFAULT_COMMANDS.get(key, key.replace("_", ""))
    success = DEFAULT_SUCCESS_AR.get(key, "تم بنجاح")
    feats = list(getattr(spec, "features", None) or [])
    feats.append(
        Feature(
            id=key,
            feature=key,
            actor=getattr(cap, "default_actor", "user") or "user",
            target="telegram_user" if getattr(cap, "needs_target_user", False) else "",
            trigger=Trigger(type="command", id=cmd),
            permissions=list(getattr(cap, "permissions", None) or []),
            action=Action(service=cap.service, method=cap.method),
            messages=Messages(success=success, failure="فشل التنفيذ"),
            success={"message": success},
            failure={"message": "فشل التنفيذ"},
        )
    )
    try:
        spec.features = feats
    except Exception:
        return False
    return True


def _protected_features_from_request(request: str) -> set[str]:
    """Features the user explicitly asked for via /slash — never strip these."""
    try:
        from telegram_bot_engine.spec_core.command_map import protected_features
        return protected_features(request or "")
    except Exception:
        return set()


def _filter_features(
    spec: Any,
    deny_exact: set[str],
    deny_prefixes: tuple[str, ...],
    *,
    protect: set[str] | None = None,
) -> list[str]:
    stripped: list[str] = []
    protect = protect or set()
    feats = list(getattr(spec, "features", None) or [])
    keep = []
    for f in feats:
        fid = _fid(f)
        if not fid:
            keep.append(f)
            continue
        base = fid[:-3] if fid.endswith("_cb") else fid
        # Root: user-written slash capabilities survive domain strip
        if fid in protect or base in protect:
            keep.append(f)
            continue
        if fid in deny_exact or any(fid.startswith(p) for p in deny_prefixes):
            stripped.append(fid)
            continue
        if base in deny_exact or any(base.startswith(p) for p in deny_prefixes):
            stripped.append(fid)
            continue
        keep.append(f)
    try:
        spec.features = keep
    except Exception:
        pass
    # start_buttons
    buttons = list(getattr(spec, "start_buttons", None) or [])
    if buttons and stripped:
        strip_set = set(stripped)
        try:
            spec.start_buttons = [
                b for b in buttons
                if not any(s in str(getattr(b, "callback_id", "")) for s in ("ticket", "clinic", "shop", "cart", "book"))
                or "task" in str(getattr(b, "callback_id", ""))
            ]
        except Exception:
            pass
    return stripped


def _fix_bot_identity(spec: Any, primary: str | None) -> list[str]:
    warnings: list[str] = []
    bot = getattr(spec, "bot", None)
    if bot is None:
        return warnings
    name = str(getattr(bot, "name", "") or "")
    desc = str(getattr(bot, "description", "") or "")
    if primary in {"tasks", "projects"}:
        if any(x in name.lower() for x in ("clinic", "shop", "market", "commerce", "booking")):
            try:
                bot.name = "tasks_bot"
                warnings.append(f"renamed_bot:{name}->tasks_bot")
            except Exception:
                pass
        if any(x in desc.lower() for x in ("clinic", "commerce", "shop suite", "marketplace")):
            try:
                bot.description = "بوت مهام شخصية"
                warnings.append("reset_tasks_description")
            except Exception:
                pass
    elif primary == "healthcare":
        if "tasks_bot" == name.lower():
            try:
                bot.name = "clinic_bot"
                warnings.append("renamed_bot:tasks_bot->clinic_bot")
            except Exception:
                pass
    elif primary == "ecommerce":
        if any(x in name.lower() for x in ("clinic", "tasks_bot")):
            try:
                bot.name = "shop_bot"
                warnings.append(f"renamed_bot:{name}->shop_bot")
            except Exception:
                pass
    return warnings


def accept_spec(
    spec: Any,
    request: str,
    *,
    decision: DomainDecision | None = None,
    repair: bool = True,
) -> GateResult:
    """Validate and repair *spec* against *request* intent. Always safe to call."""
    if spec is None:
        return GateResult(ok=False, errors=["null_spec"])

    dec = decision or decide(request or "")
    stripped: list[str] = []
    injected: list[str] = []
    errors: list[str] = []
    warnings: list[str] = []
    # Root: never strip features the user named with /slash commands
    protect = _protected_features_from_request(request or "")

    primary = dec.primary
    conf = float(getattr(dec, "confidence", 0.0) or 0.0)

    # ── tasks / projects lock ──────────────────────────────────────────
    if primary in {"tasks", "projects"} and conf >= 0.45:
        stripped.extend(_filter_features(spec, set(_TASKS_DENY_EXACT), _TASKS_DENY_PREFIXES, protect=protect))
        if repair:
            for key in _TASKS_REQUIRE:
                if key not in set(_feature_ids(spec)):
                    if _append_feature(spec, key):
                        injected.append(key)
            # keep lean optionals only if already present after strip — no force
        ids_after = set(_feature_ids(spec))
        if not (ids_after & set(_TASKS_REQUIRE)):
            errors.append("tasks_primary_missing_task_caps")
        warnings.extend(_fix_bot_identity(spec, primary))

    # ── healthcare ─────────────────────────────────────────────────────
    elif primary == "healthcare" and conf >= 0.45:
        stripped.extend(_filter_features(spec, set(_CLINIC_DENY_EXACT), _CLINIC_DENY_PREFIXES, protect=protect))
        ids_after = set(_feature_ids(spec))
        if not any(
            i.startswith("clinic_") or i.startswith("book_") or i in {"book_slot"}
            for i in ids_after
        ):
            if repair and _append_feature(spec, "clinic_book"):
                injected.append("clinic_book")
            else:
                warnings.append("healthcare_without_clinic_caps")
        warnings.extend(_fix_bot_identity(spec, primary))

    # ── ecommerce ──────────────────────────────────────────────────────
    # Threshold 0.35: Arabic shop briefs often score ~0.40 and were skipping
    # the lean pack, leaving catalog-only bots without cart/order commands.
    elif primary == "ecommerce" and conf >= 0.35:
        stripped.extend(_filter_features(spec, set(_SHOP_DENY_EXACT), _SHOP_DENY_PREFIXES, protect=protect))
        ids_after = set(_feature_ids(spec))
        # Lean commerce pack: browse + cart + order — matches «عرض / اختيار / طلب»
        _lean_shop = (
            "shop_catalog",
            "cart_view",
            "cart_add",
            "cart_checkout",
            "shop_my_orders",
        )
        if repair:
            for key in _lean_shop:
                if key not in ids_after and _append_feature(spec, key):
                    injected.append(key)
                    ids_after.add(key)
        if not any(i.startswith("shop_") or i.startswith("cart_") for i in ids_after):
            warnings.append("ecommerce_without_shop_caps")
        warnings.extend(_fix_bot_identity(spec, primary))

    # ── multi-domain lean packs (phase-2) ───────────────────────────────
    elif primary and conf >= 0.30:
        try:
            from .lean_packs import pack_for_domain
            pack = pack_for_domain(primary)
        except Exception:
            pack = ()
        if pack and repair:
            ids_after = set(_feature_ids(spec))
            for key in pack:
                if key not in ids_after and _append_feature(spec, key):
                    injected.append(key)
                    ids_after.add(key)
            warnings.append(f"lean_pack:{primary}:{len(pack)}")
            warnings.extend(_fix_bot_identity(spec, primary))

    # ── generic: always strip absolute nonsense if domain blocked presets
    blocked = set(getattr(dec, "blocked_presets", None) or [])
    if "clinic" in blocked:
        more = _filter_features(spec, set(_TASKS_DENY_EXACT) & {x for x in _TASKS_DENY_EXACT if "clinic" in x or x.startswith("clinic")}, ("clinic_", "patient_", "prescription_"), protect=protect)
        stripped.extend(more)
    if "shop" in blocked or "commerce_pro" in blocked:
        more = _filter_features(
            spec,
            {"shop_catalog", "cart_view", "shop_buy", "shop_orders", "shop_my_orders", "shop_add_item"},
            ("shop_", "cart_", "mkt_"),
            protect=protect,
        )
        stripped.extend(more)
    if "booking" in blocked:
        more = _filter_features(
            spec,
            {"book_slot", "book_list", "book_cancel", "book_admin_list"},
            ("book_",),
            protect=protect,
        )
        stripped.extend(more)

    # de-dupe stripped
    stripped = list(dict.fromkeys(stripped))
    injected = list(dict.fromkeys(injected))
    final_ids = _feature_ids(spec)

    ok = not errors
    return GateResult(
        ok=ok,
        stripped=stripped,
        injected=injected,
        errors=errors,
        warnings=warnings,
        decision_primary=primary,
        feature_ids_after=final_ids,
    )


__all__ = ["GateResult", "accept_spec"]
