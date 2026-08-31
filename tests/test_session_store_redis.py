"""Root fix verification: durable Telegram session via Redis-compatible store."""
from __future__ import annotations

import pytest

from lumen.bot.session_store import (
    SessionStore,
    _DURABLE_KEYS,
    _MemoryBackend,
    reset_session_store_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_session_store_for_tests()
    yield
    reset_session_store_for_tests()


def test_engine_ui_is_durable_key():
    assert "engine_ui" in _DURABLE_KEYS
    assert "lang" in _DURABLE_KEYS
    assert "lumen_welcome_shown" in _DURABLE_KEYS
    assert "multi_agent_state_id" in _DURABLE_KEYS


def test_save_load_roundtrip_and_secret_drop():
    backend = _MemoryBackend()
    store = SessionStore(client=backend)
    store.save(
        7,
        {
            "engine_ui": {"phase": "gen_type", "slots": {}},
            "pending_host": {"project_path": "/p"},
            "lang": "ar",
            "bot_token": "999:SECRETTOKEN_SHOULD_DROP",
            "github_token": "ghp_should_drop_or_seal",
            "ephemeral_scratch": "not-durable",
        },
    )
    data = store.load(7)
    assert data["engine_ui"]["phase"] == "gen_type"
    assert data["pending_host"]["project_path"] == "/p"
    assert data["lang"] == "ar"
    assert "bot_token" not in data
    assert "ephemeral_scratch" not in data


def test_hydrate_overwrites_stale_ram():
    backend = _MemoryBackend()
    store = SessionStore(client=backend)
    store.save(3, {"lang": "ar", "engine_ui": {"phase": "billing"}})
    # Simulate worker with stale RAM
    user_data = {"lang": "en", "engine_ui": {"phase": "home"}, "tmp": 1}
    store.hydrate(3, user_data)
    assert user_data["lang"] == "ar"
    assert user_data["engine_ui"]["phase"] == "billing"
    assert user_data["tmp"] == 1  # non-durable untouched


def test_save_merges_without_dropping_other_durable_keys():
    backend = _MemoryBackend()
    store = SessionStore(client=backend)
    store.save(9, {"lang": "ar", "engine_ui": {"phase": "dashboard"}})
    store.save(9, {"last_bot_request": "ابني بوت متجر"})
    data = store.load(9)
    assert data["lang"] == "ar"
    assert data["engine_ui"]["phase"] == "dashboard"
    assert data["last_bot_request"] == "ابني بوت متجر"


def test_clear_removes_session():
    backend = _MemoryBackend()
    store = SessionStore(client=backend)
    store.save(11, {"lang": "en"})
    store.clear(11)
    assert store.load(11) == {}


def test_production_requires_redis(monkeypatch):
    monkeypatch.setenv("RAILWAY_ENVIRONMENT", "production")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("JOB_REDIS_URL", raising=False)
    monkeypatch.delenv("SESSION_ALLOW_MEMORY", raising=False)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        SessionStore()


def test_local_memory_opt_in(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "dev")
    monkeypatch.setenv("SESSION_ALLOW_MEMORY", "1")
    for m in (
        "RAILWAY_ENVIRONMENT", "RENDER_SERVICE_ID", "FLY_APP_NAME",
        "K_SERVICE", "DYNO", "AWS_EXECUTION_ENV",
    ):
        monkeypatch.delenv(m, raising=False)
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("JOB_REDIS_URL", raising=False)
    store = SessionStore()
    assert store.backend == "memory"
    store.save(1, {"lang": "ar"})
    assert store.load(1)["lang"] == "ar"


def test_ptb_redis_persistence_lifecycle():
    """Official PTB BasePersistence path: update → get → refresh."""
    import asyncio
    from lumen.bot.ptb_redis_persistence import RedisPersistence

    backend = _MemoryBackend()
    store = SessionStore(client=backend)
    p = RedisPersistence(store=store, update_interval=1.0)

    async def run():
        await p.update_user_data(
            55,
            {
                "engine_ui": {"phase": "gen_slots"},
                "lang": "ar",
                "bot_token": "should-drop",
            },
        )
        all_ud = await p.get_user_data()
        assert 55 in all_ud
        assert all_ud[55]["lang"] == "ar"
        assert "bot_token" not in all_ud[55]
        ram = {"lang": "en"}
        await p.refresh_user_data(55, ram)
        assert ram["lang"] == "ar"
        assert ram["engine_ui"]["phase"] == "gen_slots"
        await p.drop_user_data(55)
        assert store.load(55) == {}

    asyncio.run(run())


def test_restart_simulation_full_cycle():
    """Simulate process A write → process B read (true restart / other worker)."""
    import asyncio
    from lumen.bot.ptb_redis_persistence import RedisPersistence

    shared = _MemoryBackend()

    async def run():
        store_a = SessionStore(client=shared)
        p_a = RedisPersistence(store=store_a, update_interval=1.0)
        ud_a = {
            "engine_ui": {"phase": "gen_slots", "slots": {"bot_type": "shop"}},
            "lang": "ar",
            "pending_run": {"project_path": "/tmp/bot"},
            "last_bot_request": "بوت متجر",
        }
        await p_a.update_user_data(1001, ud_a)

        store_b = SessionStore(client=shared)
        p_b = RedisPersistence(store=store_b, update_interval=1.0)
        all_users = await p_b.get_user_data()
        assert 1001 in all_users
        assert all_users[1001]["engine_ui"]["phase"] == "gen_slots"
        assert all_users[1001]["lang"] == "ar"
        assert all_users[1001]["pending_run"]["project_path"] == "/tmp/bot"

        ud_b = {"lang": "en"}  # stale RAM
        await p_b.refresh_user_data(1001, ud_b)
        assert ud_b["lang"] == "ar"
        assert ud_b["engine_ui"]["phase"] == "gen_slots"

    asyncio.run(run())
