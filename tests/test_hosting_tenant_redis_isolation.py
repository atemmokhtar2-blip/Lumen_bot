from __future__ import annotations

from lumen.engine.services.hosting import redis_state
from lumen.platform.tenant_isolation import host_instance_redis_key


class _Pipeline:
    def __init__(self, redis):
        self.redis = redis
        self.ops = []

    def setex(self, key, ttl, value):
        self.ops.append(("setex", key, value))
        return self

    def sadd(self, key, value):
        self.ops.append(("sadd", key, value))
        return self

    def expire(self, key, ttl):
        self.ops.append(("expire", key, ttl))
        return self

    def delete(self, key):
        self.ops.append(("delete", key))
        return self

    def srem(self, key, value):
        self.ops.append(("srem", key, value))
        return self

    def execute(self):
        for op in self.ops:
            name, key, value = op
            if name == "setex":
                self.redis.values[key] = value
            elif name == "sadd":
                self.redis.sets.setdefault(key, set()).add(value)
            elif name == "expire":
                continue
            elif name == "delete":
                self.redis.values.pop(key, None)
            elif name == "srem":
                self.redis.sets.setdefault(key, set()).discard(value)
        return []


class _Redis:
    def __init__(self):
        self.values = {}
        self.sets = {}

    def pipeline(self):
        return _Pipeline(self)

    def get(self, key):
        return self.values.get(key)

    def smembers(self, key):
        return set(self.sets.get(key, set()))


def test_tenant_host_records_never_enter_telegram_redis_namespace(monkeypatch):
    fake = _Redis()
    monkeypatch.setattr(redis_state, "_client", lambda: fake)

    redis_state.put_instance({
        "instance_id": "tenant-host",
        "user_id": 123,
        "tenant_id": "tenant/acme",
        "principal_id": "tenant:tenant/acme",
        "status": "running",
    })
    tenant_key = host_instance_redis_key("tenant-host", tenant_id="tenant/acme")
    assert tenant_key in fake.values
    assert "lumen:host:inst:tenant-host" not in fake.values

    assert len(redis_state.list_for_user(123, tenant_id="tenant/acme")) == 1
    assert redis_state.list_for_user(123) == []
    assert redis_state.get_instance("tenant-host") is None

    redis_state.put_instance({
        "instance_id": "telegram-host",
        "user_id": 123,
        "tenant_id": "",
        "principal_id": "telegram:123",
        "status": "running",
    })
    assert [x["instance_id"] for x in redis_state.list_for_user(123)] == ["telegram-host"]
    assert [x["instance_id"] for x in redis_state.list_for_user(123, tenant_id="tenant/acme")] == ["tenant-host"]

    redis_state.delete_instance("tenant-host", user_id=123, tenant_id="tenant/acme")
    assert redis_state.list_for_user(123, tenant_id="tenant/acme") == []
    assert [x["instance_id"] for x in redis_state.list_for_user(123)] == ["telegram-host"]
