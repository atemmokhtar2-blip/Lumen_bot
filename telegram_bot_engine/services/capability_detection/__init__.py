"""Capability Detection (P1) + Integration (P2) + Synthesis (P3) + Extensibility (P4).

Deterministic foundation. No web codegen. Packs extend the registry safely.
"""
from __future__ import annotations

from .engine import can_satisfy, detect_capabilities, detect_status
from .gap_journal import (
    GapRecord,
    journal_stats,
    list_open_gaps,
    mark_gap_status,
    record_gaps,
)
from .integration import (
    apply_detection_to_session,
    feature_keys,
    metadata_from_report,
    run_detection,
    telegram_preflight,
)
from .models import DetectionReport, DetectionStatus, GapItem, MatchedCapability
from .packs import (
    CapabilityPack,
    PackCapability,
    KNOWN_METHODS,
    KNOWN_SERVICES,
    approve_and_register,
    assess_capability,
    assess_pack_capabilities,
    draft_pack_from_research,
    draft_packs_from_open_gaps,
    ensure_packs_loaded,
    keyword_hits,
    load_all_packs,
    load_pack_file,
    loaded_packs,
    overlay_keys,
    register_pack,
    resolve_gap_with_pack,
    validate_pack,
)
from .pipeline_trace import fail_safe_message, pipeline_trace
from .ops import handle_ops_command, is_ops_admin, ops_enabled
from .health import (
    attach_generation_diagnostics,
    capability_system_health,
    health_summary_ar,
    smoke_generated_project,
)
from .pack_promotion import (
    auto_promote_ready,
    install_pack,
    promote_draft_file,
    promote_latest_drafts,
    promote_learned_entry,
    promotion_status,
    verify_installed,
)
from .learning_loop import (
    LearnedKBEntry,
    bootstrap_learned_kb_into_runtime,
    learning_stats,
    list_draft_packs,
    load_learned_kb,
    maybe_auto_learn,
    promote_gap_to_kb,
    run_learning_cycle,
)
from .web_research import ResearchHit, ResearchResult, research_feature, research_open_gaps, research_for_detection_gaps
from .research_spec import (
    ResearchSpec,
    list_research_specs,
    load_research_spec,
    research_spec_from_gap,
    save_research_spec,
)
from .search import nearest_keys_for_phrase, search_by_category, search_capabilities
from .synthesis import (
    SynthesisPlan,
    synthesize_for_request,
    synthesize_from_keys,
    synthesize_from_report,
)

__all__ = [
    "DetectionStatus",
    "MatchedCapability",
    "GapItem",
    "DetectionReport",
    "detect_capabilities",
    "detect_status",
    "can_satisfy",
    "search_capabilities",
    "search_by_category",
    "nearest_keys_for_phrase",
    "run_detection",
    "feature_keys",
    "apply_detection_to_session",
    "telegram_preflight",
    "metadata_from_report",
    "SynthesisPlan",
    "synthesize_from_keys",
    "synthesize_from_report",
    "synthesize_for_request",
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
    "assess_capability",
    "assess_pack_capabilities",
    "draft_pack_from_research",
    "draft_packs_from_open_gaps",
    "approve_and_register",
    "resolve_gap_with_pack",
    "GapRecord",
    "record_gaps",
    "list_open_gaps",
    "mark_gap_status",
    "journal_stats",
    "ResearchSpec",
    "save_research_spec",
    "load_research_spec",
    "list_research_specs",
    "research_spec_from_gap",
    "ResearchHit",
    "ResearchResult",
    "research_feature",
    "research_open_gaps",
    "research_for_detection_gaps",
    "LearnedKBEntry",
    "load_learned_kb",
    "promote_gap_to_kb",
    "run_learning_cycle",
    "bootstrap_learned_kb_into_runtime",
    "maybe_auto_learn",
    "install_pack",
    "promote_draft_file",
    "promote_latest_drafts",
    "promote_learned_entry",
    "promotion_status",
    "auto_promote_ready",
]
