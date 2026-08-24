"""Integration tests for LiveRunner / Docker isolation.

Uses testcontainers when available and TBE_TESTCONTAINERS=1.
Otherwise tests are skipped (CI can enable the flag with Docker socket).
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


def _tc_enabled() -> bool:
    return (os.getenv("TBE_TESTCONTAINERS") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


@pytest.fixture(scope="module")
def docker_available():
    try:
        from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
            docker_available,
        )
        return docker_available()
    except Exception:
        return False


def test_live_runner_host_process_refused():
    """Host process path must fail closed (Docker only)."""
    from telegram_bot_engine.services.live_runner.parts.runner import LiveRunnerService

    report = LiveRunnerService().run(
        project_path="/tmp/nonexistent_bot_project",
        bot_token="0000000000:FAKE_TOKEN_FOR_TEST_ONLY_XXXXXXXX",
        run_seconds=5,
    )
    assert report.ok is False
    assert any(
        x in (report.errors or []) or x in (report.message or "")
        for x in ("host_process_removed", "docker_required", "Docker")
    ) or "docker" in (report.message or "").lower() or "host" in (report.message or "").lower()


def test_isolation_policy_docker_only():
    from telegram_bot_engine.services.isolation_policy import decide_isolation

    d = decide_isolation()
    assert d.require_docker is True
    assert d.allow_local is False


@pytest.mark.skipif(not _tc_enabled(), reason="TBE_TESTCONTAINERS not enabled")
def test_postgres_testcontainer_smoke():
    pytest.importorskip("testcontainers")
    from testcontainers.postgres import PostgresContainer

    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        assert "postgresql" in url
        # basic connectivity
        import sqlalchemy
        engine = sqlalchemy.create_engine(url)
        with engine.connect() as conn:
            row = conn.execute(sqlalchemy.text("SELECT 1")).scalar()
            assert row == 1


@pytest.mark.skipif(not _tc_enabled(), reason="TBE_TESTCONTAINERS not enabled")
def test_docker_daemon_via_testcontainers(docker_available):
    if not docker_available:
        pytest.skip("docker daemon not available")
    pytest.importorskip("testcontainers")
    from testcontainers.core.container import DockerContainer

    # ephemeral alpine that exits immediately
    c = DockerContainer("alpine:3.19").with_command("echo tbe_ok")
    c.start()
    try:
        # container started under testcontainers control
        assert c.get_wrapped_container() is not None
    finally:
        c.stop()
