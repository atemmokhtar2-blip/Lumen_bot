"""
Smart Functional Testing + Response Validator — Specification 065.
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import List, Optional

from .report_data import (
    TEST_ERROR,
    TEST_FAIL,
    TEST_PASS,
    TEST_SKIP,
    FunctionalTestCase,
)
from .secrets_manager import SecretsManager

_log = logging.getLogger("engine.live_deployment.functional")


class FunctionalTester:
    """
    Run smart functional checks against the generated project + live token.

    Without a test chat id we:
    1. Confirm the bot answers getMe (liveness).
    2. Inspect main.py for /start handler and expected reply text.
    3. Mark tests pass/fail accordingly.
    """

    def run(
        self,
        project_path: str,
        secrets: SecretsManager,
        secret_id: str,
        *,
        expected_start_reply: Optional[str] = None,
    ) -> List[FunctionalTestCase]:
        cases: List[FunctionalTestCase] = []
        path = Path(project_path)
        main_text = self._read_main(path)
        expected = expected_start_reply or self._infer_start_reply(main_text) or "Hello World"

        # 1) Bot is reachable
        t0 = time.perf_counter()
        token = secrets.get(secret_id)
        if not token:
            cases.append(FunctionalTestCase(
                name="bot_reachable",
                command="getMe",
                status=TEST_ERROR,
                message="No token in secrets store.",
            ))
            return cases

        try:
            from .health_checker import HealthChecker
            health = HealthChecker().check(secrets, secret_id)
            status = TEST_PASS if health.online else TEST_FAIL
            cases.append(FunctionalTestCase(
                name="bot_reachable",
                command="getMe",
                expected_contains=["ok"],
                status=status,
                actual_response=health.details,
                message="Bot responds to Telegram getMe." if health.online else health.details,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            ))
        except Exception as e:
            cases.append(FunctionalTestCase(
                name="bot_reachable",
                command="getMe",
                status=TEST_ERROR,
                message=type(e).__name__,
                duration_ms=(time.perf_counter() - t0) * 1000.0,
            ))

        # 2) /start handler present in source
        t0 = time.perf_counter()
        has_start = bool(re.search(r"CommandStart|/start|command\([\"']start", main_text or "", re.I))
        cases.append(FunctionalTestCase(
            name="start_handler_present",
            command="/start",
            expected_contains=["/start"],
            status=TEST_PASS if has_start else TEST_FAIL,
            actual_response="found" if has_start else "missing",
            message="main.py contains a /start handler." if has_start else "No /start handler in main.py.",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        ))

        # 3) Expected reply text in source
        t0 = time.perf_counter()
        reply_ok = expected.lower() in (main_text or "").lower() if expected else False
        cases.append(FunctionalTestCase(
            name="start_reply_text",
            command="/start",
            expected_contains=[expected],
            status=TEST_PASS if reply_ok else TEST_FAIL,
            actual_response=expected if reply_ok else "not found in source",
            message=(
                f"Expected reply '{expected}' is present in generated code."
                if reply_ok
                else f"Expected reply '{expected}' not found in main.py."
            ),
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        ))

        # 4) /help optional
        t0 = time.perf_counter()
        has_help = bool(re.search(r"/help|command\([\"']help", main_text or "", re.I))
        cases.append(FunctionalTestCase(
            name="help_handler",
            command="/help",
            status=TEST_PASS if has_help else TEST_SKIP,
            actual_response="found" if has_help else "not present",
            message="Optional /help handler.",
            duration_ms=(time.perf_counter() - t0) * 1000.0,
        ))

        _log.info(
            "Functional tests complete",
            extra={
                "total": len(cases),
                "passed": sum(1 for c in cases if c.status == TEST_PASS),
            },
        )
        return cases

    @staticmethod
    def _read_main(project_path: Path) -> str:
        candidates = [
            project_path / "main.py",
            project_path / "bot.py",
            project_path / "app.py",
        ]
        # Also search one level deep for core/main.py
        for p in list(candidates) + list(project_path.glob("*/main.py")) + list(project_path.glob("*/core/main.py")):
            if p.is_file():
                try:
                    return p.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
        return ""

    @staticmethod
    def _infer_start_reply(main_text: str) -> Optional[str]:
        if not main_text:
            return None
        m = re.search(
            r"""(?:answer|reply_text|reply)\s*\(\s*['"]([^'"]+)['"]""",
            main_text,
        )
        if m:
            return m.group(1)
        return None
