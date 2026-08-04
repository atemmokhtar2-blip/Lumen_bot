"""
E2E Scenario Testing Report (Specification 044 — ULTRA CRITICAL).

End-to-end scenario testing as a real user would use the bot.
Any failed scenario blocks delivery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_UNIT_TEST = "unit_test_generation_report"
SOURCE_INTEGRATION = "integration_verification_report"
SOURCE_RUNTIME = "runtime_simulation_report"
SOURCE_ARCHITECTURE = "architecture_compliance_report"
SOURCE_SELF_HEALING = "self_healing_report"
SOURCE_PROJECT_CONTEXT = "project_context_report"

ALL_SOURCES = (
    SOURCE_UNIT_TEST,
    SOURCE_INTEGRATION,
    SOURCE_RUNTIME,
    SOURCE_ARCHITECTURE,
    SOURCE_SELF_HEALING,
    SOURCE_PROJECT_CONTEXT,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Scenario kinds
SCN_NORMAL = "normal_usage"
SCN_FAST = "fast_usage"
SCN_RANDOM = "random_usage"
SCN_WRONG = "wrong_usage"
SCN_INTENSE = "intense_usage"
SCN_NEGATIVE = "negative"
SCN_EDGE = "edge_case"
SCN_LOAD = "load"
SCN_RECOVERY = "recovery"
SCN_UX = "user_experience"

ALL_SCENARIO_KINDS = (
    SCN_NORMAL, SCN_FAST, SCN_RANDOM, SCN_WRONG, SCN_INTENSE,
    SCN_NEGATIVE, SCN_EDGE, SCN_LOAD, SCN_RECOVERY, SCN_UX,
)

# Telegram interaction types
TG_COMMAND = "command"
TG_BUTTON = "button"
TG_INLINE = "inline_button"
TG_CALLBACK = "callback_query"
TG_FILE = "file"
TG_PHOTO = "photo"
TG_VIDEO = "video"
TG_DOCUMENT = "document"
TG_VOICE = "voice"
TG_LOCATION = "location"
TG_CONTACT = "contact"
TG_POLL = "poll"
TG_GROUP = "group_event"
TG_CHANNEL = "channel_event"
TG_TEXT = "text_message"

ALL_TG_TYPES = (
    TG_COMMAND, TG_BUTTON, TG_INLINE, TG_CALLBACK, TG_FILE, TG_PHOTO,
    TG_VIDEO, TG_DOCUMENT, TG_VOICE, TG_LOCATION, TG_CONTACT, TG_POLL,
    TG_GROUP, TG_CHANNEL, TG_TEXT,
)

RULE_NO_SCENARIO_FAILURE = "no_scenario_failure"
RULE_LOAD_OK = "load_simulation_ok"
RULE_RECOVERY_OK = "recovery_ok"
RULE_UX_OK = "ux_acceptable"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"
RULE_SUFFICIENT_CONFIDENCE = "sufficient_confidence"

ALL_QUALITY_RULES = (
    RULE_NO_SCENARIO_FAILURE,
    RULE_LOAD_OK,
    RULE_RECOVERY_OK,
    RULE_UX_OK,
    RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS,
    RULE_SUFFICIENT_CONFIDENCE,
)

MIN_UX_SCORE = 70.0
MIN_SUCCESS_RATE = 95.0

CACHE_HIT = "hit"
CACHE_MISS = "miss"
CACHE_DISABLED = "disabled"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_HIGH_THRESHOLD = 0.85
CONFIDENCE_MEDIUM_THRESHOLD = 0.60

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)

STATUS_PASSED = "passed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"
STATUS_WARNING = "warning"


@dataclass
class VirtualUser:
    user_id: str
    language: str = "en"
    speed: str = "normal"  # slow|normal|fast
    style: str = "typical"  # typical|power|confused|malicious
    permissions: str = "user"  # user|admin|restricted

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "language": self.language,
            "speed": self.speed,
            "style": self.style,
            "permissions": self.permissions,
        }


@dataclass
class ScenarioStep:
    step_id: str
    action_type: str
    payload: str = ""
    expected: str = ""
    actual: str = ""
    status: str = STATUS_PASSED
    latency_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "action_type": self.action_type,
            "payload": self.payload[:200] if self.payload else "",
            "expected": self.expected,
            "actual": self.actual,
            "status": self.status,
            "latency_ms": self.latency_ms,
        }


@dataclass
class ScenarioResult:
    scenario_id: str
    scenario_kind: str
    user_id: str = ""
    status: str = STATUS_PASSED
    severity: str = SEVERITY_INFO
    message: str = ""
    steps: List[ScenarioStep] = field(default_factory=list)
    duration_ms: float = 0.0
    unexpected_behavior: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "scenario_kind": self.scenario_kind,
            "user_id": self.user_id,
            "status": self.status,
            "severity": self.severity,
            "message": self.message,
            "steps": [s.to_dict() for s in self.steps],
            "duration_ms": self.duration_ms,
            "unexpected_behavior": self.unexpected_behavior,
        }


@dataclass
class LoadResult:
    users: int
    concurrent: int = 0
    success_rate: float = 100.0
    avg_latency_ms: float = 0.0
    p99_latency_ms: float = 0.0
    errors: int = 0
    status: str = STATUS_PASSED
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "users": self.users,
            "concurrent": self.concurrent,
            "success_rate": self.success_rate,
            "avg_latency_ms": self.avg_latency_ms,
            "p99_latency_ms": self.p99_latency_ms,
            "errors": self.errors,
            "status": self.status,
            "notes": self.notes,
        }


@dataclass
class RecoveryResult:
    recovery_id: str
    failure_type: str
    recovered: bool = True
    status: str = STATUS_PASSED
    message: str = ""
    recovery_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recovery_id": self.recovery_id,
            "failure_type": self.failure_type,
            "recovered": self.recovered,
            "status": self.status,
            "message": self.message,
            "recovery_ms": self.recovery_ms,
        }


@dataclass
class UXScore:
    response_speed: float = 0.0
    message_clarity: float = 0.0
    step_order: float = 0.0
    ease_of_use: float = 0.0
    overall: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "response_speed": self.response_speed,
            "message_clarity": self.message_clarity,
            "step_order": self.step_order,
            "ease_of_use": self.ease_of_use,
            "overall": self.overall,
        }


@dataclass
class E2EFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "e2e"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
            "resolution_hint": self.resolution_hint,
            "category": self.category,
        }


@dataclass
class CacheInfo:
    status: str = CACHE_MISS
    key: str = ""
    created_at: str = ""
    hits: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status,
            "key": self.key,
            "created_at": self.created_at,
            "hits": self.hits,
        }


@dataclass
class E2EProvenance:
    engine_name: str = "e2e_scenario_testing"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    self_verification_passed: bool = False
    runs_completed: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "sources_used": list(self.sources_used),
            "sources_missing": list(self.sources_missing),
            "generated_at": self.generated_at,
            "confidence": self.confidence,
            "confidence_level": self.confidence_level,
            "self_verification_passed": self.self_verification_passed,
            "runs_completed": self.runs_completed,
        }


@dataclass
class E2EScenarioTestingReport:
    report_id: str = ""
    users: List[VirtualUser] = field(default_factory=list)
    scenarios: List[ScenarioResult] = field(default_factory=list)
    load_results: List[LoadResult] = field(default_factory=list)
    recoveries: List[RecoveryResult] = field(default_factory=list)
    ux: UXScore = field(default_factory=UXScore)
    findings: List[E2EFinding] = field(default_factory=list)
    scenario_count: int = 0
    failed_count: int = 0
    unexpected_count: int = 0
    success_rate: float = 0.0
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: E2EProvenance = field(default_factory=E2EProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "users": [u.to_dict() for u in self.users],
            "scenarios": [s.to_dict() for s in self.scenarios],
            "load_results": [l.to_dict() for l in self.load_results],
            "recoveries": [r.to_dict() for r in self.recoveries],
            "ux": self.ux.to_dict(),
            "findings": [f.to_dict() for f in self.findings],
            "scenario_count": self.scenario_count,
            "failed_count": self.failed_count,
            "unexpected_count": self.unexpected_count,
            "success_rate": self.success_rate,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_UNIT_TEST", "SOURCE_INTEGRATION", "SOURCE_RUNTIME",
    "SOURCE_ARCHITECTURE", "SOURCE_SELF_HEALING", "SOURCE_PROJECT_CONTEXT",
    "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "SCN_NORMAL", "SCN_FAST", "SCN_RANDOM", "SCN_WRONG", "SCN_INTENSE",
    "SCN_NEGATIVE", "SCN_EDGE", "SCN_LOAD", "SCN_RECOVERY", "SCN_UX",
    "ALL_SCENARIO_KINDS",
    "TG_COMMAND", "TG_BUTTON", "TG_INLINE", "TG_CALLBACK", "TG_FILE", "TG_PHOTO",
    "TG_VIDEO", "TG_DOCUMENT", "TG_VOICE", "TG_LOCATION", "TG_CONTACT", "TG_POLL",
    "TG_GROUP", "TG_CHANNEL", "TG_TEXT", "ALL_TG_TYPES",
    "RULE_NO_SCENARIO_FAILURE", "RULE_LOAD_OK", "RULE_RECOVERY_OK", "RULE_UX_OK",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "RULE_SUFFICIENT_CONFIDENCE",
    "ALL_QUALITY_RULES",
    "MIN_UX_SCORE", "MIN_SUCCESS_RATE",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "STATUS_PASSED", "STATUS_FAILED", "STATUS_SKIPPED", "STATUS_WARNING",
    "VirtualUser", "ScenarioStep", "ScenarioResult", "LoadResult", "RecoveryResult",
    "UXScore", "E2EFinding", "CacheInfo", "E2EProvenance", "E2EScenarioTestingReport",
]
