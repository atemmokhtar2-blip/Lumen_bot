"""Integration tests — LiveRunner fail-closed + optional testcontainers."""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.integration


def _tc_enabled() -> bool:
    return (os.getenv("TBE_TESTCONTAINERS") or "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def test_live_runner_host_process_refused():
    from lumen.engine.services.live_runner.parts.runner import LiveRunnerService

    report = LiveRunnerService().run(
        project_path="/tmp/nonexistent_bot_project_xyz",
        bot_token="0000000000:FAKE_TOKEN_FOR_TEST_ONLY_XXXXXXXX",
        run_seconds=5,
    )
    assert report.ok is False
    blob = f"{report.message} {' '.join(report.errors or [])}".lower()
    assert any(x in blob for x in ("host_process", "docker", "security", "removed", "required"))


def test_isolation_policy_docker_only():
    from lumen.engine.services.isolation_policy import decide_isolation

    d = decide_isolation()
    assert d.require_docker is True
    assert d.allow_local is False


def test_openapi_spec_exists_and_has_generate():
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "api" / "openapi.yaml"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "openapi:" in text
    assert "/generate" in text
    assert "ApiKeyAuth" in text


@pytest.mark.skipif(not _tc_enabled(), reason="TBE_TESTCONTAINERS not enabled")
def test_postgres_testcontainer_smoke():
    pytest.importorskip("testcontainers")
    from testcontainers.postgres import PostgresContainer
    import sqlalchemy

    with PostgresContainer("postgres:16-alpine") as pg:
        url = pg.get_connection_url()
        engine = sqlalchemy.create_engine(url)
        with engine.connect() as conn:
            assert conn.execute(sqlalchemy.text("SELECT 1")).scalar() == 1


@pytest.mark.skipif(not _tc_enabled(), reason="TBE_TESTCONTAINERS not enabled")
def test_redis_testcontainer_smoke():
    pytest.importorskip("testcontainers")
    pytest.importorskip("redis")
    from testcontainers.redis import RedisContainer

    with RedisContainer("redis:7-alpine") as rc:
        client = rc.get_client()
        client.set("tbe_test", "1")
        assert client.get("tbe_test") in {b"1", "1"}
