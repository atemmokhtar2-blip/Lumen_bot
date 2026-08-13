"""
Report data models — Specification 065 Live Deployment & Smart Testing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Sources / constants
# ---------------------------------------------------------------------------

SOURCE_PROJECT = "project_output"
SOURCE_USER_TOKEN = "user_token"
SOURCE_DEPLOYMENT = "deployment_provider"
SOURCE_HEALTH = "health_check"
SOURCE_FUNCTIONAL = "functional_tests"
SOURCE_RUNTIME = "runtime"
SOURCE_LOGS = "logs"

ALL_SOURCES = (
    SOURCE_PROJECT,
    SOURCE_USER_TOKEN,
    SOURCE_DEPLOYMENT,
    SOURCE_HEALTH,
    SOURCE_FUNCTIONAL,
    SOURCE_RUNTIME,
    SOURCE_LOGS,
)

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_STOPPED = "stopped"
STATUS_FAILED = "failed"
STATUS_SUCCESS = "success"
STATUS_SKIPPED = "skipped"

DEPLOY_PENDING = "pending"
DEPLOY_BUILDING = "building"
DEPLOY_DEPLOYING = "deploying"
DEPLOY_RUNNING = "running"
DEPLOY_STOPPED = "stopped"
DEPLOY_FAILED = "failed"
DEPLOY_CRASHED = "crashed"

VERDICT_READY = "ready"
VERDICT_READY_WITH_WARNINGS = "ready_with_warnings"
VERDICT_NOT_READY = "not_ready"

SEVERITY_CRITICAL = "critical"
SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"
SEVERITY_INFO = "info"

TEST_PASS = "pass"
TEST_FAIL = "fail"
TEST_SKIP = "skip"
TEST_ERROR = "error"

MIN_QUALITY_SCORE = 0.7
MAX_REPAIR_ATTEMPTS = 3

RULE_TOKEN_VALID = "token_valid"
RULE_OWNERSHIP_OK = "ownership_verified"
RULE_SECRETS_SAFE = "secrets_not_logged"
RULE_DEPLOY_OK = "deployment_successful"
RULE_HEALTH_OK = "health_check_passed"
RULE_FUNCTIONAL_OK = "functional_tests_passed"
RULE_NO_RUNTIME_ERRORS = "no_runtime_errors"

ALL_QUALITY_RULES = (
    RULE_TOKEN_VALID,
    RULE_OWNERSHIP_OK,
    RULE_SECRETS_SAFE,
    RULE_DEPLOY_OK,
    RULE_HEALTH_OK,
    RULE_FUNCTIONAL_OK,
    RULE_NO_RUNTIME_ERRORS,
)


@dataclass
class TokenValidationResult:
    valid: bool = False
    bot_id: Optional[int] = None
    bot_username: str = ""
    bot_name: str = ""
    can_join_groups: bool = False
    can_read_messages: bool = False
    error: str = ""
    ownership_verified: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "bot_id": self.bot_id,
            "bot_username": self.bot_username,
            "bot_name": self.bot_name,
            "can_join_groups": self.can_join_groups,
            "can_read_messages": self.can_read_messages,
            "error": self.error,
            "ownership_verified": self.ownership_verified,
            # NEVER include the raw token
        }


@dataclass
class DeploymentStatus:
    provider: str = "railway"
    deployment_id: str = ""
    service_id: str = ""
    project_id: str = ""
    status: str = DEPLOY_PENDING
    url: str = ""
    message: str = ""
    dry_run: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "provider": self.provider,
            "deployment_id": self.deployment_id,
            "service_id": self.service_id,
            "project_id": self.project_id,
            "status": self.status,
            "url": self.url,
            "message": self.message,
            "dry_run": self.dry_run,
        }


@dataclass
class HealthCheckResult:
    online: bool = False
    polling_or_webhook_ok: bool = False
    telegram_reachable: bool = False
    latency_ms: float = 0.0
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "online": self.online,
            "polling_or_webhook_ok": self.polling_or_webhook_ok,
            "telegram_reachable": self.telegram_reachable,
            "latency_ms": self.latency_ms,
            "details": self.details,
        }


@dataclass
class FunctionalTestCase:
    name: str
    command: str
    expected_contains: List[str] = field(default_factory=list)
    status: str = TEST_SKIP
    actual_response: str = ""
    message: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "expected_contains": list(self.expected_contains),
            "status": self.status,
            "actual_response": self.actual_response[:500],
            "message": self.message,
            "duration_ms": self.duration_ms,
        }


@dataclass
class RuntimeErrorRecord:
    error_type: str = ""
    message: str = ""
    file: str = ""
    line: int = 0
    function: str = ""
    engine: str = "live_deployment"
    traceback: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.error_type,
            "message": self.message,
            "file": self.file,
            "line": self.line,
            "function": self.function,
            "engine": self.engine,
            "traceback": self.traceback[:2000],
        }


@dataclass
class DeploymentFinding:
    severity: str = SEVERITY_INFO
    code: str = ""
    message: str = ""
    affected: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "affected": self.affected,
        }


@dataclass
class LiveDeploymentReport:
    """Full report for Specification 065."""

    engine_name: str = "live_deployment"
    project_path: str = ""
    token_validation: Optional[TokenValidationResult] = None
    deployment: Optional[DeploymentStatus] = None
    health: Optional[HealthCheckResult] = None
    functional_tests: List[FunctionalTestCase] = field(default_factory=list)
    runtime_errors: List[RuntimeErrorRecord] = field(default_factory=list)
    findings: List[DeploymentFinding] = field(default_factory=list)
    logs_tail: List[str] = field(default_factory=list)
    repair_attempts: int = 0
    max_repair_attempts: int = MAX_REPAIR_ATTEMPTS
    quality_score: float = 0.0
    verdict: str = VERDICT_NOT_READY
    passed: bool = False
    env_written: bool = False
    secrets_stored: bool = False

    @property
    def tests_total(self) -> int:
        return len(self.functional_tests)

    @property
    def tests_passed(self) -> int:
        return sum(1 for t in self.functional_tests if t.status == TEST_PASS)

    @property
    def tests_failed(self) -> int:
        return sum(1 for t in self.functional_tests if t.status in (TEST_FAIL, TEST_ERROR))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "project_path": self.project_path,
            "token_validation": (
                self.token_validation.to_dict() if self.token_validation else None
            ),
            "deployment": self.deployment.to_dict() if self.deployment else None,
            "health": self.health.to_dict() if self.health else None,
            "functional_tests": [t.to_dict() for t in self.functional_tests],
            "runtime_errors": [e.to_dict() for e in self.runtime_errors],
            "findings": [f.to_dict() for f in self.findings],
            "logs_tail": list(self.logs_tail[-50:]),
            "repair_attempts": self.repair_attempts,
            "max_repair_attempts": self.max_repair_attempts,
            "quality_score": self.quality_score,
            "verdict": self.verdict,
            "passed": self.passed,
            "env_written": self.env_written,
            "secrets_stored": self.secrets_stored,
            "tests_total": self.tests_total,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
        }


ALL_VERDICTS = (VERDICT_READY, VERDICT_READY_WITH_WARNINGS, VERDICT_NOT_READY)
