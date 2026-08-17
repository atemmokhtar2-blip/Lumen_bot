def _saas_pack(*, limit: int = 72) -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "saas", "seat", "plan3", "billing2", "meter", "quota", "subscription2",
            "trial2", "addon2", "workspace2", "org", "team2", "rbac", "flag2",
            "webhook3", "apikey", "oauth2",
        ),
        limit=limit,
        extra=_SAAS_CAPS,
    )


def _marketplace_pack(*, limit: int = 72) -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "mkt", "listing2", "vendor2", "buyer", "offer2", "bid2", "escrow",
            "payout2", "commission2", "catalog2", "storefront", "auction3",
            "rfq2", "quote2", "dispute3", "review3",
        ),
        limit=limit,
        extra=_MARKETPLACE_CAPS,
    )


def _logistics_pack(*, limit: int = 72) -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "logi", "ship4", "fleet2", "route3", "hub2", "dock2", "warehouse4",
            "courier2", "manifest", "lane", "container", "lastmile", "pod2",
            "eta2", "load2", "trip",
        ),
        limit=limit,
        extra=("start", "help", "order_track", "order_status", "lang"),
    )


def _finance_pack(*, limit: int = 72) -> tuple[str, ...]:
    return _pack_from_prefixes(
        (
            "fin", "ledger2", "journal", "payout3", "settle2", "recon", "treasury",
            "fx", "card3", "wallet3", "loan2", "credit2", "limit2", "kyc2", "aml2",
            "invoice4", "receivable", "payable", "tax3", "fee2",
        ),
        limit=limit,
        extra=("start", "help", "wallet_balance", "wallet_topup", "lang"),
    )

_COMMUNITY_CAPS = tuple(_PRESET_DATA.get("_COMMUNITY_CAPS", ()))
_EVENTS_CAPS = tuple(_PRESET_DATA.get("_EVENTS_CAPS", ()))
_WALLET_CAPS = tuple(_PRESET_DATA.get("_WALLET_CAPS", ()))
# Creator monetization (digital content + tips + membership gate)
_CREATOR_CAPS = tuple(_PRESET_DATA.get("_CREATOR_CAPS", ()))
# All-in-one commerce pro — densest market pack for launch day
_COMMERCE_PRO_CAPS = tuple(dict.fromkeys(
    list(_SHOP_CAPS)
    + list(_SUB_CAPS)
    + list(_POINTS_CAPS)
    + list(_GROWTH_CAPS)
    + list(_WALLET_CAPS)
    + [
        "payment_precheckout", "payment_success", "analytics_overview",
        "analytics_revenue", "admin_users", "coupon_create", "refund_request",
        "refund_approve", "stock_set", "broadcast_segment",
    ]
))

_CREATOR_KEYS = tuple(_PRESET_DATA.get("_CREATOR_KEYS", ()))
_COMMERCE_PRO_KEYS = tuple(_PRESET_DATA.get("_COMMERCE_PRO_KEYS", ()))

_GROWTH_KEYS = tuple(_PRESET_DATA.get("_GROWTH_KEYS", ()))
_CRM_KEYS = tuple(_PRESET_DATA.get("_CRM_KEYS", ()))
_EDU_KEYS = tuple(_PRESET_DATA.get("_EDU_KEYS", ()))
_RESTAURANT_KEYS = tuple(_PRESET_DATA.get("_RESTAURANT_KEYS", ()))
_JOBS_KEYS = tuple(_PRESET_DATA.get("_JOBS_KEYS", ()))
_MARKETPLACE_KEYS = tuple(_PRESET_DATA.get("_MARKETPLACE_KEYS", ()))
_SAAS_KEYS = tuple(_PRESET_DATA.get("_SAAS_KEYS", ()))
_LOGISTICS_KEYS = tuple(_PRESET_DATA.get("_LOGISTICS_KEYS", ()))
_FINANCE_KEYS = tuple(_PRESET_DATA.get("_FINANCE_KEYS", ()))
_COMMUNITY_KEYS = tuple(_PRESET_DATA.get("_COMMUNITY_KEYS", ()))
_EVENTS_KEYS = tuple(_PRESET_DATA.get("_EVENTS_KEYS", ()))
_WALLET_KEYS = tuple(_PRESET_DATA.get("_WALLET_KEYS", ()))
_SUPPORT_PRO_KEYS = tuple(_PRESET_DATA.get("_SUPPORT_PRO_KEYS", ()))



_FITNESS_CAPS = tuple(_PRESET_DATA.get("_FITNESS_CAPS", ()))
_REALESTATE_CAPS = tuple(_PRESET_DATA.get("_REALESTATE_CAPS", ()))
_CLINIC_CAPS = tuple(_PRESET_DATA.get("_CLINIC_CAPS", ()))
_AUCTION_CAPS = tuple(_PRESET_DATA.get("_AUCTION_CAPS", ()))
_DELIVERY_CAPS = tuple(_PRESET_DATA.get("_DELIVERY_CAPS", ()))

_FITNESS_KEYS = tuple(_PRESET_DATA.get("_FITNESS_KEYS", ()))
_REALESTATE_KEYS = tuple(_PRESET_DATA.get("_REALESTATE_KEYS", ()))
_CLINIC_KEYS = tuple(_PRESET_DATA.get("_CLINIC_KEYS", ()))
_AUCTION_KEYS = tuple(_PRESET_DATA.get("_AUCTION_KEYS", ()))
_DELIVERY_KEYS = tuple(_PRESET_DATA.get("_DELIVERY_KEYS", ()))

# Modern verticals (zero-AI keyword packs)
_IOT_KEYS = tuple(_PRESET_DATA.get("_IOT_KEYS", ()))
_BLOCKCHAIN_KEYS = tuple(_PRESET_DATA.get("_BLOCKCHAIN_KEYS", ()))
_AI_KEYS = tuple(_PRESET_DATA.get("_AI_KEYS", ()))
_DEVOPS_KEYS = tuple(_PRESET_DATA.get("_DEVOPS_KEYS", ()))
_GAMING_KEYS = tuple(_PRESET_DATA.get("_GAMING_KEYS", ()))

_IOT_CAPS = tuple(_PRESET_DATA.get("_IOT_CAPS", ()))
_BLOCKCHAIN_CAPS = tuple(_PRESET_DATA.get("_BLOCKCHAIN_CAPS", ()))
_AI_CAPS = tuple(_PRESET_DATA.get("_AI_CAPS", ()))
_DEVOPS_CAPS = tuple(_PRESET_DATA.get("_DEVOPS_CAPS", ()))
_GAMING_CAPS = tuple(_PRESET_DATA.get("_GAMING_CAPS", ()))


