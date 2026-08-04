"""
Message Queue Report (Specification 062 — MAXIMUM CRITICAL).

Central message queue between engines and services: priority/FIFO/delayed/
retry queues, reliable delivery, deduplication, persistence, DLQ.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


SOURCE_SERVICE = "service_management_report"
SOURCE_SECURITY = "security_permission_report"
SOURCE_MONITORING = "system_monitoring_report"
SOURCE_ORCHESTRATOR = "engine_orchestrator_report"
SOURCE_EXECUTION_CONTEXT = "execution_context_report"
SOURCE_USER_REQUEST = "user_request"

ALL_SOURCES = (
    SOURCE_SERVICE,
    SOURCE_SECURITY,
    SOURCE_MONITORING,
    SOURCE_ORCHESTRATOR,
    SOURCE_EXECUTION_CONTEXT,
    SOURCE_USER_REQUEST,
)

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

# Queue kinds
QUEUE_PRIORITY = "priority"
QUEUE_FIFO = "fifo"
QUEUE_DELAYED = "delayed"
QUEUE_RETRY = "retry"
QUEUE_DLQ = "dead_letter"

ALL_QUEUE_KINDS = (
    QUEUE_PRIORITY, QUEUE_FIFO, QUEUE_DELAYED, QUEUE_RETRY, QUEUE_DLQ,
)

# Message status
MSG_PENDING = "pending"
MSG_DELIVERED = "delivered"
MSG_FAILED = "failed"
MSG_RETRYING = "retrying"
MSG_DEAD = "dead"
MSG_DUPLICATE = "duplicate"

ALL_MSG_STATUS = (
    MSG_PENDING, MSG_DELIVERED, MSG_FAILED, MSG_RETRYING, MSG_DEAD, MSG_DUPLICATE,
)

RULE_NO_LOSS = "no_message_loss"
RULE_NO_DUPLICATE = "no_unintended_duplicate"
RULE_ORDERING = "ordering_preserved"
RULE_RETRY_POLICY = "retry_policy_applied"
RULE_SELF_VERIFICATION = "self_verification_passed"
RULE_QUALITY_PASS = "quality_pass"

ALL_QUALITY_RULES = (
    RULE_NO_LOSS,
    RULE_NO_DUPLICATE,
    RULE_ORDERING,
    RULE_RETRY_POLICY,
    RULE_SELF_VERIFICATION,
    RULE_QUALITY_PASS,
)

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

DEFAULT_MAX_RETRIES = 3


@dataclass
class QueueMessage:
    message_id: str
    payload: str = ""
    source: str = ""
    destination: str = ""
    priority: int = 100  # lower = higher priority
    queue_kind: str = QUEUE_FIFO
    status: str = MSG_PENDING
    retry_count: int = 0
    max_retries: int = DEFAULT_MAX_RETRIES
    ordered_group: str = ""
    dedupe_key: str = ""
    created_at: str = ""
    delivered_at: str = ""
    persistent: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "payload": self.payload,
            "source": self.source,
            "destination": self.destination,
            "priority": self.priority,
            "queue_kind": self.queue_kind,
            "status": self.status,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
            "ordered_group": self.ordered_group,
            "dedupe_key": self.dedupe_key,
            "created_at": self.created_at,
            "delivered_at": self.delivered_at,
            "persistent": self.persistent,
        }


@dataclass
class DeliveryRecord:
    message_id: str
    attempt: int
    success: bool
    timestamp: str
    error: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "attempt": self.attempt,
            "success": self.success,
            "timestamp": self.timestamp,
            "error": self.error,
        }


@dataclass
class RetryRecord:
    message_id: str
    attempt: int
    next_delay_ms: int = 0
    reason: str = ""
    timestamp: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "attempt": self.attempt,
            "next_delay_ms": self.next_delay_ms,
            "reason": self.reason,
            "timestamp": self.timestamp,
        }


@dataclass
class DeadLetterRecord:
    message_id: str
    original_queue: str
    reason: str
    retry_count: int = 0
    timestamp: str = ""
    payload_snippet: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "original_queue": self.original_queue,
            "reason": self.reason,
            "retry_count": self.retry_count,
            "timestamp": self.timestamp,
            "payload_snippet": self.payload_snippet,
        }


@dataclass
class QueueStats:
    queue_kind: str
    size: int = 0
    processing_rate: float = 0.0
    retry_count: int = 0
    failed_count: int = 0
    delivered_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "queue_kind": self.queue_kind,
            "size": self.size,
            "processing_rate": self.processing_rate,
            "retry_count": self.retry_count,
            "failed_count": self.failed_count,
            "delivered_count": self.delivered_count,
        }


@dataclass
class QueueFinding:
    severity: str
    code: str
    message: str
    affected: str = ""
    resolution_hint: str = ""
    category: str = "queue"

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
class QueueProvenance:
    engine_name: str = "message_queue"
    engine_version: str = "1.0.0"
    sources_used: List[str] = field(default_factory=list)
    sources_missing: List[str] = field(default_factory=list)
    generated_at: str = ""
    confidence: float = 0.0
    confidence_level: str = CONFIDENCE_LOW
    self_verification_passed: bool = False

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
        }


@dataclass
class MessageQueueReport:
    report_id: str = ""
    messages: List[QueueMessage] = field(default_factory=list)
    deliveries: List[DeliveryRecord] = field(default_factory=list)
    retries: List[RetryRecord] = field(default_factory=list)
    dead_letters: List[DeadLetterRecord] = field(default_factory=list)
    stats: List[QueueStats] = field(default_factory=list)
    findings: List[QueueFinding] = field(default_factory=list)
    message_count: int = 0
    delivered_count: int = 0
    failed_count: int = 0
    retry_count: int = 0
    dlq_count: int = 0
    duplicate_count: int = 0
    lost_count: int = 0
    self_verification_passed: bool = False
    readiness_status: str = VERDICT_NOT_READY
    verdict: str = VERDICT_NOT_READY
    cache_info: CacheInfo = field(default_factory=CacheInfo)
    provenance: QueueProvenance = field(default_factory=QueueProvenance)
    metadata: Dict[str, Any] = field(default_factory=dict)
    is_empty: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "messages": [m.to_dict() for m in self.messages],
            "deliveries": [d.to_dict() for d in self.deliveries],
            "retries": [r.to_dict() for r in self.retries],
            "dead_letters": [d.to_dict() for d in self.dead_letters],
            "stats": [s.to_dict() for s in self.stats],
            "findings": [f.to_dict() for f in self.findings],
            "message_count": self.message_count,
            "delivered_count": self.delivered_count,
            "failed_count": self.failed_count,
            "retry_count": self.retry_count,
            "dlq_count": self.dlq_count,
            "duplicate_count": self.duplicate_count,
            "lost_count": self.lost_count,
            "self_verification_passed": self.self_verification_passed,
            "readiness_status": self.readiness_status,
            "verdict": self.verdict,
            "cache_info": self.cache_info.to_dict(),
            "provenance": self.provenance.to_dict(),
            "metadata": dict(self.metadata),
            "is_empty": self.is_empty,
        }


__all__ = [
    "SOURCE_SERVICE", "SOURCE_SECURITY", "SOURCE_MONITORING",
    "SOURCE_ORCHESTRATOR", "SOURCE_EXECUTION_CONTEXT", "SOURCE_USER_REQUEST", "ALL_SOURCES",
    "SEVERITY_CRITICAL", "SEVERITY_HIGH", "SEVERITY_MEDIUM", "SEVERITY_LOW", "SEVERITY_INFO",
    "QUEUE_PRIORITY", "QUEUE_FIFO", "QUEUE_DELAYED", "QUEUE_RETRY", "QUEUE_DLQ", "ALL_QUEUE_KINDS",
    "MSG_PENDING", "MSG_DELIVERED", "MSG_FAILED", "MSG_RETRYING", "MSG_DEAD", "MSG_DUPLICATE",
    "ALL_MSG_STATUS",
    "RULE_NO_LOSS", "RULE_NO_DUPLICATE", "RULE_ORDERING", "RULE_RETRY_POLICY",
    "RULE_SELF_VERIFICATION", "RULE_QUALITY_PASS", "ALL_QUALITY_RULES",
    "CACHE_HIT", "CACHE_MISS", "CACHE_DISABLED",
    "CONFIDENCE_HIGH", "CONFIDENCE_MEDIUM", "CONFIDENCE_LOW",
    "CONFIDENCE_HIGH_THRESHOLD", "CONFIDENCE_MEDIUM_THRESHOLD",
    "VERDICT_READY", "VERDICT_READY_WITH_WARNINGS", "VERDICT_NOT_READY", "ALL_VERDICTS",
    "DEFAULT_MAX_RETRIES",
    "QueueMessage", "DeliveryRecord", "RetryRecord", "DeadLetterRecord",
    "QueueStats", "QueueFinding", "CacheInfo", "QueueProvenance", "MessageQueueReport",
]
