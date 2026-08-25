"""Capability integrity checks — structural guarantees for the registry + presets.

Run: python -m lumen.engine.spec_core.capability_integrity
"""
from __future__ import annotations

import re
from collections import defaultdict

from .presets import (
    _COMMERCE_PRO_CAPS,
    _CREATOR_CAPS,
    _GROWTH_CAPS,
    _POINTS_CAPS,
    _SAAS_CAPS,
    _SHOP_CAPS,
    _SUB_CAPS,
    detect_preset,
    session_for_preset,
)
from .registry import CAPABILITIES, by_category, get_capability


_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_ACTORS = {"user", "admin", "owner", "any"}


def audit() -> list[str]:
    errors: list[str] = []
    for k, c in CAPABILITIES.items():
        if k != c.key:
            errors.append(f"key mismatch {k}!={c.key}")
        if not _ID.match(c.key) or not _ID.match(c.service) or not _ID.match(c.method):
            errors.append(f"bad identifier on {k}")
        if c.default_actor not in _ACTORS:
            errors.append(f"bad actor on {k}: {c.default_actor}")
        if not c.description_en or not c.description_ar:
            errors.append(f"missing description on {k}")

    for pack_name, caps in {
        "shop": _SHOP_CAPS,
        "sub": _SUB_CAPS,
        "points": _POINTS_CAPS,
        "growth": _GROWTH_CAPS,
        "creator": _CREATOR_CAPS,
        "saas": _SAAS_CAPS,
        "commerce_pro": _COMMERCE_PRO_CAPS,
    }.items():
        for key in caps:
            if not get_capability(key):
                errors.append(f"preset {pack_name} unknown capability {key}")

    for q in (
        "متجر متكامل",
        "اشتراكات",
        "نقاط",
        "creator content",
        "saas analytics",
        "إحالة",
    ):
        p = detect_preset(q)
        if not p:
            errors.append(f"no preset for {q!r}")
            continue
        try:
            spec = session_for_preset(p).to_spec()
            if not spec.features:
                errors.append(f"empty features for {p}")
        except Exception as exc:
            errors.append(f"to_spec {p}: {exc}")

    return errors


def main() -> None:
    errs = audit()
    print(f"capabilities={len(CAPABILITIES)} categories={len(by_category())}")
    if errs:
        print(f"FAIL {len(errs)}")
        for e in errs[:50]:
            print(" -", e)
        raise SystemExit(1)
    print("OK — registry + presets integrity passed")


if __name__ == "__main__":
    main()
