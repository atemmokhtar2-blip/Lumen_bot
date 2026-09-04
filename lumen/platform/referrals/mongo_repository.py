"""MongoDB ReferralRepository — real persistence for the referral program.

Hard rules enforced here:
  - referred_telegram_id is unique (one referrer only)
  - self-referral rejected at domain factory
  - only status=qualified counts toward REFERRAL_QUALIFIED_TARGET
  - link-open creates pending; bot-use calls mark_qualified
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

from lumen.domain.entities.referral import Referral, ReferralError, ReferralStats
from lumen.domain.value_objects.referral_status import ReferralStatus
from lumen.platform.referrals.config import (
    REFERRAL_COLLECTION,
    REFERRAL_STATS_COLLECTION,
)
from lumen.platform.referrals.schema import REFERRAL_INDEXES, REFERRAL_STATS_INDEXES

logger = logging.getLogger(__name__)


def _doc_to_referral(doc: dict[str, Any] | None) -> Optional[Referral]:
    if not doc:
        return None
    return Referral(
        referrer_telegram_id=int(doc.get("referrer_telegram_id") or 0),
        referred_telegram_id=int(doc.get("referred_telegram_id") or 0),
        status=ReferralStatus(str(doc.get("status") or "pending")),
        created_at=float(doc.get("created_at") or 0.0),
        qualified_at=(
            float(doc["qualified_at"])
            if doc.get("qualified_at") is not None
            else None
        ),
        reward_batch_id=doc.get("reward_batch_id"),
        metadata=dict(doc.get("metadata") or {}),
    )


class MongoReferralRepository:
    def __init__(self, uri: str | None = None, *, db_name: str | None = None) -> None:
        try:
            from pymongo import ASCENDING, MongoClient
            from pymongo.errors import DuplicateKeyError
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("pymongo is required for referrals") from exc

        self._DuplicateKeyError = DuplicateKeyError
        self.uri = (uri or os.getenv("MONGODB_URI") or "").strip()
        if not self.uri:
            raise ValueError("MONGODB_URI is required for MongoReferralRepository")
        self.db_name = (db_name or os.getenv("MONGODB_DB") or "lumen").strip()
        timeout = int(os.getenv("MONGODB_TIMEOUT_MS") or "3000")
        self._client = MongoClient(
            self.uri,
            serverSelectionTimeoutMS=timeout,
            connectTimeoutMS=timeout,
            retryWrites=True,
        )
        self._db = self._client[self.db_name]
        self.col = self._db[REFERRAL_COLLECTION]
        self.stats = self._db[REFERRAL_STATS_COLLECTION]
        self.ensure_indexes()

    def ensure_indexes(self) -> None:
        from pymongo import ASCENDING

        try:
            for spec in REFERRAL_INDEXES:
                keys = [(k, int(v)) for k, v in spec["keys"]]
                self.col.create_index(
                    keys,
                    unique=bool(spec.get("unique")),
                    name=str(spec.get("name") or "idx"),
                )
            for spec in REFERRAL_STATS_INDEXES:
                keys = [(k, int(v)) for k, v in spec["keys"]]
                self.stats.create_index(
                    keys,
                    unique=bool(spec.get("unique")),
                    name=str(spec.get("name") or "idx"),
                )
        except Exception as exc:
            logger.warning("referral index setup deferred: %s", type(exc).__name__)

    def create_pending(
        self, referrer_telegram_id: int, referred_telegram_id: int
    ) -> Referral:
        from lumen.platform.referrals.config import REFERRAL_MAX_PER_REFERRER

        ref = Referral.create_pending(referrer_telegram_id, referred_telegram_id)
        if self.count_for_referrer(ref.referrer_telegram_id) >= int(REFERRAL_MAX_PER_REFERRER):
            raise ReferralError("referrer_invite_cap_reached")
        doc = {
            "referrer_telegram_id": ref.referrer_telegram_id,
            "referred_telegram_id": ref.referred_telegram_id,
            "status": ReferralStatus.PENDING.value,
            "created_at": ref.created_at,
            "qualified_at": None,
            "reward_batch_id": None,
            "metadata": {},
        }
        try:
            self.col.insert_one(doc)
        except self._DuplicateKeyError as exc:
            raise ReferralError("referred_already_registered") from exc
        # Race-safe cap: parallel inserts can pass pre-check — roll back if over max
        if self.count_for_referrer(ref.referrer_telegram_id) > int(REFERRAL_MAX_PER_REFERRER):
            try:
                self.col.delete_one({"referred_telegram_id": ref.referred_telegram_id})
            except Exception:
                logger.warning("referral over-cap rollback failed", exc_info=True)
            raise ReferralError("referrer_invite_cap_reached")
        self._bump_stats(ref.referrer_telegram_id, pending_delta=1, invited_delta=1)
        return ref

    def get_by_referred(self, referred_telegram_id: int) -> Optional[Referral]:
        doc = self.col.find_one({"referred_telegram_id": int(referred_telegram_id)})
        return _doc_to_referral(doc)

    def mark_qualified(self, referred_telegram_id: int) -> Optional[Referral]:
        """Only pending → qualified. Already qualified returns current row."""
        from pymongo import ReturnDocument

        rid = int(referred_telegram_id)
        existing = self.get_by_referred(rid)
        if existing is None:
            return None
        if existing.status is ReferralStatus.QUALIFIED:
            return existing
        if existing.status is ReferralStatus.REJECTED:
            raise ReferralError("cannot_qualify_rejected_referral")
        now = time.time()
        doc = self.col.find_one_and_update(
            {
                "referred_telegram_id": rid,
                "status": ReferralStatus.PENDING.value,
            },
            {
                "$set": {
                    "status": ReferralStatus.QUALIFIED.value,
                    "qualified_at": now,
                }
            },
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return self.get_by_referred(rid)
        ref = _doc_to_referral(doc)
        if ref and ref.status is ReferralStatus.QUALIFIED:
            self._bump_stats(
                ref.referrer_telegram_id, pending_delta=-1, qualified_delta=1
            )
        return ref

    def count_qualified(self, referrer_telegram_id: int) -> int:
        return int(
            self.col.count_documents(
                {
                    "referrer_telegram_id": int(referrer_telegram_id),
                    "status": ReferralStatus.QUALIFIED.value,
                }
            )
        )

    def count_for_referrer(self, referrer_telegram_id: int) -> int:
        return int(
            self.col.count_documents(
                {"referrer_telegram_id": int(referrer_telegram_id)}
            )
        )

    def stats_for(self, referrer_telegram_id: int) -> ReferralStats:
        rid = int(referrer_telegram_id)
        doc = self.stats.find_one({"referrer_telegram_id": rid})
        if doc:
            return ReferralStats(
                referrer_telegram_id=rid,
                total_invited=int(doc.get("total_invited") or 0),
                qualified_count=int(doc.get("qualified_count") or 0),
                pending_count=int(doc.get("pending_count") or 0),
                rejected_count=int(doc.get("rejected_count") or 0),
                reward_paid=bool(doc.get("reward_paid")),
                reward_batch_id=doc.get("reward_batch_id"),
            )
        # rebuild from referrals if stats missing
        return self._rebuild_stats(rid)


    def claim_reward_slot(
        self,
        referrer_telegram_id: int,
        *,
        batch_id: str,
        min_qualified: int,
    ) -> bool:
        """CAS: reward_paid false + qualified_count >= target → paid true."""
        from pymongo import ReturnDocument

        rid = int(referrer_telegram_id)
        bid = str(batch_id or "").strip()
        if not bid:
            return False
        # Prefer live count over possibly stale stats counter
        live = self.count_qualified(rid)
        if live < int(min_qualified):
            return False
        doc = self.stats.find_one_and_update(
            {
                "referrer_telegram_id": rid,
                "reward_paid": {"$ne": True},
            },
            {
                "$set": {
                    "reward_paid": True,
                    "reward_batch_id": bid,
                    "qualified_count": live,
                    "updated_at": time.time(),
                },
                "$setOnInsert": {
                    "total_invited": live,
                    "pending_count": 0,
                    "rejected_count": 0,
                },
            },
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        if not doc:
            return False
        # If another worker already set a different batch, we lost
        return str(doc.get("reward_batch_id") or "") == bid and bool(doc.get("reward_paid"))

    def release_reward_slot(self, referrer_telegram_id: int) -> None:
        rid = int(referrer_telegram_id)
        self.stats.update_one(
            {"referrer_telegram_id": rid, "reward_paid": True},
            {
                "$set": {
                    "reward_paid": False,
                    "reward_batch_id": None,
                    "updated_at": time.time(),
                }
            },
        )

    def mark_reward_paid(
        self, referrer_telegram_id: int, *, batch_id: str
    ) -> ReferralStats:
        rid = int(referrer_telegram_id)
        bid = str(batch_id or "").strip()
        if not bid:
            raise ReferralError("reward_batch_id_required")
        self.stats.update_one(
            {"referrer_telegram_id": rid},
            {
                "$set": {
                    "reward_paid": True,
                    "reward_batch_id": bid,
                    "updated_at": time.time(),
                }
            },
            upsert=True,
        )
        return self.stats_for(rid)

    def _bump_stats(
        self,
        referrer_telegram_id: int,
        *,
        invited_delta: int = 0,
        pending_delta: int = 0,
        qualified_delta: int = 0,
        rejected_delta: int = 0,
    ) -> None:
        rid = int(referrer_telegram_id)
        self.stats.update_one(
            {"referrer_telegram_id": rid},
            {
                "$inc": {
                    "total_invited": int(invited_delta),
                    "pending_count": int(pending_delta),
                    "qualified_count": int(qualified_delta),
                    "rejected_count": int(rejected_delta),
                },
                "$setOnInsert": {
                    "reward_paid": False,
                    "reward_batch_id": None,
                },
                "$set": {"updated_at": time.time()},
            },
            upsert=True,
        )

    def _rebuild_stats(self, referrer_telegram_id: int) -> ReferralStats:
        rid = int(referrer_telegram_id)
        pipeline = [
            {"$match": {"referrer_telegram_id": rid}},
            {"$group": {"_id": "$status", "n": {"$sum": 1}}},
        ]
        counts = {d["_id"]: int(d["n"]) for d in self.col.aggregate(pipeline)}
        stats = ReferralStats(
            referrer_telegram_id=rid,
            total_invited=sum(counts.values()),
            qualified_count=int(counts.get(ReferralStatus.QUALIFIED.value, 0)),
            pending_count=int(counts.get(ReferralStatus.PENDING.value, 0)),
            rejected_count=int(counts.get(ReferralStatus.REJECTED.value, 0)),
            reward_paid=False,
        )
        self.stats.update_one(
            {"referrer_telegram_id": rid},
            {
                "$set": {
                    "total_invited": stats.total_invited,
                    "qualified_count": stats.qualified_count,
                    "pending_count": stats.pending_count,
                    "rejected_count": stats.rejected_count,
                    "updated_at": time.time(),
                },
                "$setOnInsert": {"reward_paid": False, "reward_batch_id": None},
            },
            upsert=True,
        )
        return stats



    def top_referrers(self, *, limit: int = 10) -> list[dict]:
        """Top referrers by qualified count (admin leaderboard)."""
        lim = max(1, min(50, int(limit or 10)))
        try:
            cur = self.stats.find(
                {"qualified_count": {"$gt": 0}},
                projection={
                    "referrer_telegram_id": 1,
                    "qualified_count": 1,
                    "total_invited": 1,
                    "pending_count": 1,
                    "reward_paid": 1,
                },
            ).sort("qualified_count", -1).limit(lim)
            out = []
            for d in cur:
                out.append(
                    {
                        "referrer_telegram_id": int(d.get("referrer_telegram_id") or 0),
                        "qualified_count": int(d.get("qualified_count") or 0),
                        "total_invited": int(d.get("total_invited") or 0),
                        "pending_count": int(d.get("pending_count") or 0),
                        "reward_paid": bool(d.get("reward_paid")),
                    }
                )
            return out
        except Exception:
            logger.warning("top_referrers failed", exc_info=True)
            return []

class MemoryReferralRepository:
    """In-process store for unit tests (same behavioural surface)."""

    def __init__(self) -> None:
        self._by_referred: dict[int, Referral] = {}
        self._reward_paid: dict[int, tuple[bool, str | None]] = {}

    def ensure_indexes(self) -> None:
        return None

    def create_pending(
        self, referrer_telegram_id: int, referred_telegram_id: int
    ) -> Referral:
        from lumen.platform.referrals.config import REFERRAL_MAX_PER_REFERRER

        ref = Referral.create_pending(referrer_telegram_id, referred_telegram_id)
        if ref.referred_telegram_id in self._by_referred:
            raise ReferralError("referred_already_registered")
        if self.count_for_referrer(ref.referrer_telegram_id) >= int(REFERRAL_MAX_PER_REFERRER):
            raise ReferralError("referrer_invite_cap_reached")
        self._by_referred[ref.referred_telegram_id] = ref
        if self.count_for_referrer(ref.referrer_telegram_id) > int(REFERRAL_MAX_PER_REFERRER):
            self._by_referred.pop(ref.referred_telegram_id, None)
            raise ReferralError("referrer_invite_cap_reached")
        return ref

    def get_by_referred(self, referred_telegram_id: int) -> Optional[Referral]:
        return self._by_referred.get(int(referred_telegram_id))

    def mark_qualified(self, referred_telegram_id: int) -> Optional[Referral]:
        ref = self._by_referred.get(int(referred_telegram_id))
        if ref is None:
            return None
        ref.qualify()
        return ref

    def count_qualified(self, referrer_telegram_id: int) -> int:
        rid = int(referrer_telegram_id)
        return sum(
            1
            for r in self._by_referred.values()
            if r.referrer_telegram_id == rid and r.is_countable()
        )

    def count_for_referrer(self, referrer_telegram_id: int) -> int:
        rid = int(referrer_telegram_id)
        return sum(
            1 for r in self._by_referred.values() if r.referrer_telegram_id == rid
        )

    def stats_for(self, referrer_telegram_id: int) -> ReferralStats:
        rid = int(referrer_telegram_id)
        rows = [r for r in self._by_referred.values() if r.referrer_telegram_id == rid]
        paid, batch = self._reward_paid.get(rid, (False, None))
        return ReferralStats(
            referrer_telegram_id=rid,
            total_invited=len(rows),
            qualified_count=sum(1 for r in rows if r.is_countable()),
            pending_count=sum(
                1 for r in rows if r.status is ReferralStatus.PENDING
            ),
            rejected_count=sum(
                1 for r in rows if r.status is ReferralStatus.REJECTED
            ),
            reward_paid=paid,
            reward_batch_id=batch,
        )


    def claim_reward_slot(
        self,
        referrer_telegram_id: int,
        *,
        batch_id: str,
        min_qualified: int,
    ) -> bool:
        rid = int(referrer_telegram_id)
        if self.count_qualified(rid) < int(min_qualified):
            return False
        paid, _ = self._reward_paid.get(rid, (False, None))
        if paid:
            return False
        self._reward_paid[rid] = (True, str(batch_id))
        return True

    def release_reward_slot(self, referrer_telegram_id: int) -> None:
        self._reward_paid.pop(int(referrer_telegram_id), None)

    def mark_reward_paid(
        self, referrer_telegram_id: int, *, batch_id: str
    ) -> ReferralStats:
        self._reward_paid[int(referrer_telegram_id)] = (True, str(batch_id))
        return self.stats_for(referrer_telegram_id)


    def top_referrers(self, *, limit: int = 10) -> list[dict]:
        lim = max(1, min(50, int(limit or 10)))
        by: dict[int, dict] = {}
        for r in self._by_referred.values():
            d = by.setdefault(
                r.referrer_telegram_id,
                {
                    "referrer_telegram_id": r.referrer_telegram_id,
                    "qualified_count": 0,
                    "total_invited": 0,
                    "pending_count": 0,
                    "reward_paid": False,
                },
            )
            d["total_invited"] += 1
            if r.is_countable():
                d["qualified_count"] += 1
            elif r.status is ReferralStatus.PENDING:
                d["pending_count"] += 1
        for rid, (paid, _) in self._reward_paid.items():
            if rid in by:
                by[rid]["reward_paid"] = bool(paid)
        rows = sorted(
            by.values(), key=lambda x: int(x["qualified_count"]), reverse=True
        )
        return rows[:lim]


_repo: MongoReferralRepository | MemoryReferralRepository | None = None


def get_referral_repository():
    """Mongo when MONGODB_URI set; memory otherwise (local tests)."""
    global _repo
    if _repo is not None:
        return _repo
    if (os.getenv("MONGODB_URI") or "").strip():
        _repo = MongoReferralRepository()
    else:
        _repo = MemoryReferralRepository()
    return _repo


def reset_referral_repository_for_tests() -> None:
    global _repo
    _repo = None
