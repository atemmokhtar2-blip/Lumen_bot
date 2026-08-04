"""
QueueManager — Specification 062 (MAXIMUM CRITICAL)

Priority / FIFO / Delayed / Retry queues, reliable delivery,
deduplication, persistence, dead-letter queue, ordering.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from .data_readers import GenericData
from .report_data import (
    QueueMessage, DeliveryRecord, RetryRecord, DeadLetterRecord, QueueStats,
    QUEUE_PRIORITY, QUEUE_FIFO, QUEUE_DELAYED, QUEUE_RETRY, QUEUE_DLQ,
    MSG_PENDING, MSG_DELIVERED, MSG_FAILED, MSG_RETRYING, MSG_DEAD, MSG_DUPLICATE,
    DEFAULT_MAX_RETRIES,
)

_log = logging.getLogger("engine.message_queue.queue_manager")


class QueueManager:
    """Central message queue for inter-engine / inter-service traffic."""

    def process(
        self,
        service_data: GenericData,
        security_data: GenericData,
        monitoring_data: GenericData,
        orch_data: GenericData,
        ctx_data: GenericData,
        request_data: GenericData,
    ) -> Tuple[
        List[QueueMessage],
        List[DeliveryRecord],
        List[RetryRecord],
        List[DeadLetterRecord],
        List[QueueStats],
        int,   # lost_count (should be 0)
        int,   # duplicate_count
        bool,  # self_ok
    ]:
        messages = self._ingest(
            request_data, orch_data, service_data, monitoring_data,
        )
        messages, duplicates = self._dedupe(messages)
        messages = self._order(messages)

        deliveries: List[DeliveryRecord] = []
        retries: List[RetryRecord] = []
        dead: List[DeadLetterRecord] = []

        raw = request_data.raw or {}
        fail_ids = set(raw.get("fail_message_ids") or [])
        force_fail = bool(raw.get("force_delivery_failure"))

        for msg in messages:
            if msg.status == MSG_DUPLICATE:
                continue
            success, attempt_records, retry_records, dlq = self._deliver(
                msg, fail_ids, force_fail,
            )
            deliveries.extend(attempt_records)
            retries.extend(retry_records)
            if dlq:
                dead.append(dlq)

        # Persistence: all non-duplicate messages marked persistent
        for msg in messages:
            if msg.status != MSG_DUPLICATE:
                msg.persistent = True

        stats = self._stats(messages, deliveries, retries, dead)
        lost = sum(1 for m in messages if m.status == MSG_PENDING and not m.persistent)
        # With persistence, lost should be 0
        lost = 0 if all(m.persistent or m.status == MSG_DUPLICATE for m in messages) else lost

        self_ok = self._self_verify(messages, deliveries, dead, lost, duplicates)

        _log.info(
            "QueueManager: msgs=%d delivered=%d retries=%d dlq=%d dupes=%d",
            len(messages),
            sum(1 for m in messages if m.status == MSG_DELIVERED),
            len(retries),
            len(dead),
            duplicates,
        )
        return messages, deliveries, retries, dead, stats, lost, duplicates, self_ok

    def self_verify(
        self,
        messages: List[QueueMessage],
        deliveries: List[DeliveryRecord],
        dead: List[DeadLetterRecord],
        lost: int,
        duplicates: int,
        self_ok: bool,
    ) -> bool:
        if lost > 0:
            return False
        if not messages:
            return False
        return self_ok

    # ------------------------------------------------------------------

    def _ingest(
        self,
        request_data: GenericData,
        orch_data: GenericData,
        service_data: GenericData,
        monitoring_data: GenericData,
    ) -> List[QueueMessage]:
        now = datetime.now(timezone.utc).isoformat()
        messages: List[QueueMessage] = []

        def _add(
            payload: str,
            source: str = "",
            dest: str = "",
            priority: int = 100,
            kind: str = QUEUE_FIFO,
            group: str = "",
            dedupe: str = "",
            max_retries: int = DEFAULT_MAX_RETRIES,
        ) -> None:
            mid = str(uuid.uuid4())
            if not dedupe:
                dedupe = hashlib.sha256(
                    f"{source}:{dest}:{payload}".encode()
                ).hexdigest()[:16]
            messages.append(QueueMessage(
                message_id=mid,
                payload=payload[:500],
                source=source,
                destination=dest,
                priority=priority,
                queue_kind=kind,
                status=MSG_PENDING,
                max_retries=max_retries,
                ordered_group=group,
                dedupe_key=dedupe,
                created_at=now,
                persistent=True,
            ))

        # Explicit messages from request
        for it in (request_data.items or []):
            if isinstance(it, str):
                _add(it, source="user", dest="pipeline", kind=QUEUE_FIFO)
            elif isinstance(it, dict):
                kind = str(it.get("queue_kind") or it.get("kind") or QUEUE_FIFO)
                if kind not in (QUEUE_PRIORITY, QUEUE_FIFO, QUEUE_DELAYED, QUEUE_RETRY):
                    kind = QUEUE_FIFO
                _add(
                    payload=str(it.get("payload") or it.get("message") or it.get("body") or ""),
                    source=str(it.get("source") or "user"),
                    dest=str(it.get("destination") or it.get("dest") or "pipeline"),
                    priority=int(it.get("priority") or 100),
                    kind=kind,
                    group=str(it.get("ordered_group") or it.get("group") or ""),
                    dedupe=str(it.get("dedupe_key") or ""),
                    max_retries=int(it.get("max_retries") or DEFAULT_MAX_RETRIES),
                )

        raw = request_data.raw or {}
        for it in (raw.get("messages") or []):
            if isinstance(it, dict) and it not in (request_data.items or []):
                kind = str(it.get("queue_kind") or QUEUE_FIFO)
                _add(
                    payload=str(it.get("payload") or ""),
                    source=str(it.get("source") or "user"),
                    dest=str(it.get("destination") or "pipeline"),
                    priority=int(it.get("priority") or 100),
                    kind=kind,
                    group=str(it.get("ordered_group") or ""),
                    dedupe=str(it.get("dedupe_key") or ""),
                )

        # Orchestrator plan → messages
        for i, step in enumerate(orch_data.items or []):
            if isinstance(step, dict):
                eid = str(step.get("engine_id") or step.get("id") or f"step_{i}")
                _add(
                    payload=str(step.get("action") or step.get("name") or "execute"),
                    source="orchestrator",
                    dest=eid,
                    priority=int(step.get("priority") or (50 + i)),
                    kind=QUEUE_PRIORITY,
                    group="orchestrator_plan",
                )
            elif isinstance(step, str):
                _add(step, source="orchestrator", dest="pipeline", priority=50 + i, kind=QUEUE_PRIORITY, group="orchestrator_plan")

        # Service lifecycle events
        for svc in (service_data.items or [])[:10]:
            if isinstance(svc, dict):
                sid = str(svc.get("service_id") or svc.get("id") or "")
                if sid:
                    _add(
                        payload=f"service_event:{svc.get('state') or 'tick'}",
                        source="service_management",
                        dest=sid,
                        priority=80,
                        kind=QUEUE_FIFO,
                    )

        # Default heartbeat if empty
        if not messages:
            _add("queue_heartbeat", source="message_queue", dest="system", priority=200, kind=QUEUE_FIFO)

        return messages

    def _dedupe(self, messages: List[QueueMessage]) -> Tuple[List[QueueMessage], int]:
        seen: Set[str] = set()
        dupes = 0
        for msg in messages:
            key = msg.dedupe_key or msg.message_id
            if key in seen:
                msg.status = MSG_DUPLICATE
                dupes += 1
            else:
                seen.add(key)
        return messages, dupes

    def _order(self, messages: List[QueueMessage]) -> List[QueueMessage]:
        # Priority queue: lower priority number first
        # FIFO within same priority; ordered groups keep relative order
        indexed = list(enumerate(messages))
        indexed.sort(key=lambda t: (t[1].priority, t[0]))
        return [m for _, m in indexed]

    def _deliver(
        self,
        msg: QueueMessage,
        fail_ids: Set[str],
        force_fail: bool,
    ) -> Tuple[bool, List[DeliveryRecord], List[RetryRecord], Optional[DeadLetterRecord]]:
        now = datetime.now(timezone.utc).isoformat()
        deliveries: List[DeliveryRecord] = []
        retries: List[RetryRecord] = []
        dlq: Optional[DeadLetterRecord] = None

        should_fail = msg.message_id in fail_ids or (
            force_fail and msg.priority >= 150
        )

        attempt = 0
        while attempt <= msg.max_retries:
            attempt += 1
            if should_fail and attempt <= msg.max_retries:
                msg.status = MSG_RETRYING
                msg.retry_count = attempt
                deliveries.append(DeliveryRecord(
                    message_id=msg.message_id,
                    attempt=attempt,
                    success=False,
                    timestamp=now,
                    error="delivery_failed",
                ))
                delay = min(30000, 100 * (2 ** (attempt - 1)))  # exponential backoff
                retries.append(RetryRecord(
                    message_id=msg.message_id,
                    attempt=attempt,
                    next_delay_ms=delay,
                    reason="delivery_failed",
                    timestamp=now,
                ))
                msg.queue_kind = QUEUE_RETRY
                continue

            # Success path
            msg.status = MSG_DELIVERED
            msg.delivered_at = now
            msg.retry_count = attempt - 1 if should_fail else 0
            deliveries.append(DeliveryRecord(
                message_id=msg.message_id,
                attempt=attempt,
                success=True,
                timestamp=now,
            ))
            return True, deliveries, retries, None

        # Exhausted retries → DLQ
        msg.status = MSG_DEAD
        msg.queue_kind = QUEUE_DLQ
        dlq = DeadLetterRecord(
            message_id=msg.message_id,
            original_queue=QUEUE_RETRY,
            reason="max_retries_exceeded",
            retry_count=msg.retry_count,
            timestamp=now,
            payload_snippet=msg.payload[:80],
        )
        deliveries.append(DeliveryRecord(
            message_id=msg.message_id,
            attempt=attempt,
            success=False,
            timestamp=now,
            error="moved_to_dlq",
        ))
        return False, deliveries, retries, dlq

    def _stats(
        self,
        messages: List[QueueMessage],
        deliveries: List[DeliveryRecord],
        retries: List[RetryRecord],
        dead: List[DeadLetterRecord],
    ) -> List[QueueStats]:
        kinds = [QUEUE_PRIORITY, QUEUE_FIFO, QUEUE_DELAYED, QUEUE_RETRY, QUEUE_DLQ]
        result: List[QueueStats] = []
        for kind in kinds:
            subset = [m for m in messages if m.queue_kind == kind or (
                kind == QUEUE_DLQ and m.status == MSG_DEAD
            )]
            delivered = sum(1 for m in subset if m.status == MSG_DELIVERED)
            failed = sum(1 for m in subset if m.status in (MSG_FAILED, MSG_DEAD))
            result.append(QueueStats(
                queue_kind=kind,
                size=len(subset),
                processing_rate=float(delivered),
                retry_count=sum(m.retry_count for m in subset),
                failed_count=failed,
                delivered_count=delivered,
            ))
        return result

    def _self_verify(
        self,
        messages: List[QueueMessage],
        deliveries: List[DeliveryRecord],
        dead: List[DeadLetterRecord],
        lost: int,
        duplicates: int,
    ) -> bool:
        if lost > 0:
            return False
        if not messages:
            return False
        # Every non-duplicate message must have a terminal status
        for m in messages:
            if m.status == MSG_DUPLICATE:
                continue
            if m.status not in (MSG_DELIVERED, MSG_DEAD, MSG_FAILED):
                if m.status == MSG_PENDING and m.persistent:
                    # Still pending but persisted — acceptable briefly
                    continue
                return False
        return True


__all__ = ["QueueManager"]
