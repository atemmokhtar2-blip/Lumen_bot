"""Capability packs — extensible registry units with emit contract."""
from .emit_contract import (
    KNOWN_METHODS,
    KNOWN_SERVICES,
    EmitAssessment,
    assess_capability,
    assess_pack_capabilities,
    known_service_method_pairs,
)
from .loader import (
    ensure_packs_loaded,
    keyword_hits,
    load_all_packs,
    load_pack_file,
    loaded_packs,
    overlay_keys,
    register_pack,
)
from .pipeline import (
    approve_and_register,
    draft_pack_from_research,
    draft_packs_from_open_gaps,
    resolve_gap_with_pack,
)
from .schema import CapabilityPack, PackCapability, validate_pack

__all__ = [
    "CapabilityPack",
    "PackCapability",
    "validate_pack",
    "register_pack",
    "load_pack_file",
    "load_all_packs",
    "overlay_keys",
    "loaded_packs",
    "keyword_hits",
    "ensure_packs_loaded",
    "KNOWN_SERVICES",
    "KNOWN_METHODS",
    "EmitAssessment",
    "assess_capability",
    "assess_pack_capabilities",
    "known_service_method_pairs",
    "draft_pack_from_research",
    "draft_packs_from_open_gaps",
    "approve_and_register",
    "resolve_gap_with_pack",
]
