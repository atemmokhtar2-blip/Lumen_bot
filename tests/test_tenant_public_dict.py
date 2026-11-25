from datetime import datetime, timezone

from lumen.platform.tenants import Tenant


def test_public_tenant_creation_time_is_iso8601_not_unix_epoch():
    tenant = Tenant(tenant_id="tenant-test", name="Test", created_at=1_700_000_000.0)

    value = tenant.public_dict()["created_at"]

    assert value == "2023-11-14T22:13:20Z"
    assert isinstance(value, str)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc
    assert parsed.timestamp() == 1_700_000_000.0
