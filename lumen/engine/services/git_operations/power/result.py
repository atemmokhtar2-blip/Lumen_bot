"""Unified data contract for all Power Git operations — no Telegram/AI knowledge."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class GitEngineResult:
    ok: bool
    op: str = ""
    strategy_used: str = ""
    files_changed_count: int = 0
    commit_hash: Optional[str] = None
    validation_passed: bool = False
    path: Optional[str] = None
    url: Optional[str] = None
    message: str = ""
    needs_auth: bool = False
    redacted_error: str = ""
    attempts: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "op": self.op,
            "strategy_used": self.strategy_used,
            "files_changed_count": self.files_changed_count,
            "commit_hash": self.commit_hash,
            "validation_passed": self.validation_passed,
            "path": self.path,
            "url": self.url,
            "message": self.message,
            "needs_auth": self.needs_auth,
            "redacted_error": self.redacted_error,
            "attempts": self.attempts,
            "metadata": self.metadata,
        }

    @classmethod
    def fail(
        cls,
        op: str,
        *,
        message: str = "",
        redacted_error: str = "",
        needs_auth: bool = False,
        strategy_used: str = "",
        attempts: int = 0,
        url: Optional[str] = None,
        path: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "GitEngineResult":
        return cls(
            ok=False,
            op=op,
            message=message or redacted_error or "operation failed",
            redacted_error=redacted_error or message,
            needs_auth=needs_auth,
            strategy_used=strategy_used,
            attempts=attempts,
            url=url,
            path=path,
            validation_passed=False,
            metadata=dict(metadata or {}),
        )
