"""BlueprintBuilder — Specification 062"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .report_data import (
    MessageQueueReport, QueueMessage, DeliveryRecord, RetryRecord,
    DeadLetterRecord, QueueStats, CacheInfo, QueueProvenance,
    CONFIDENCE_HIGH, CONFIDENCE_MEDIUM, CONFIDENCE_LOW,
    CONFIDENCE_HIGH_THRESHOLD, CONFIDENCE_MEDIUM_THRESHOLD, VERDICT_NOT_READY,
    MSG_DELIVERED, MSG_FAILED, MSG_DEAD, MSG_DUPLICATE,
)

_log = logging.getLogger("engine.message_queue.blueprint_builder")


class BlueprintBuilder:
    def build(
        self,
        messages: List[QueueMessage],
        deliveries: List[DeliveryRecord],
        retries: List[RetryRecord],
        dead_letters: List[DeadLetterRecord],
        stats: List[QueueStats],
        sources_used: List[str],
        sources_missing: List[str],
        lost_count: int = 0,
        duplicate_count: int = 0,
        self_verification_passed: bool = False,
        cache_info: Optional[CacheInfo] = None,
        confidence: float = 0.0,
    ) -> MessageQueueReport:
        conf_level = (
            CONFIDENCE_HIGH if confidence >= CONFIDENCE_HIGH_THRESHOLD
            else CONFIDENCE_MEDIUM if confidence >= CONFIDENCE_MEDIUM_THRESHOLD
            else CONFIDENCE_LOW
        )
        delivered = sum(1 for m in messages if m.status == MSG_DELIVERED)
        failed = sum(1 for m in messages if m.status in (MSG_FAILED, MSG_DEAD))
        report = MessageQueueReport(
            report_id=str(uuid.uuid4()),
            messages=messages,
            deliveries=deliveries,
            retries=retries,
            dead_letters=dead_letters,
            stats=stats,
            findings=[],
            message_count=len(messages),
            delivered_count=delivered,
            failed_count=failed,
            retry_count=len(retries),
            dlq_count=len(dead_letters),
            duplicate_count=duplicate_count,
            lost_count=lost_count,
            self_verification_passed=self_verification_passed,
            readiness_status=VERDICT_NOT_READY,
            verdict=VERDICT_NOT_READY,
            cache_info=cache_info or CacheInfo(),
            provenance=QueueProvenance(
                engine_name="message_queue",
                engine_version="1.0.0",
                sources_used=list(sources_used),
                sources_missing=list(sources_missing),
                generated_at=datetime.now(timezone.utc).isoformat(),
                confidence=confidence,
                confidence_level=conf_level,
                self_verification_passed=self_verification_passed,
            ),
            is_empty=len(messages) == 0,
        )
        _log.info(
            "BlueprintBuilder produced %s (msgs=%d delivered=%d dlq=%d)",
            report.report_id[:8], len(messages), delivered, len(dead_letters),
        )
        return report


__all__ = ["BlueprintBuilder"]
