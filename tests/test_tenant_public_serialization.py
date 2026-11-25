from datetime import datetime, timezone

from lumen.domain.entities.tenant import Tenant


def test_public_tenant_creation_time_is_utc_iso8601_not_unix_epoch():
    created_at = 1_795_602_665.0
    payload = Tenant(
        tenant_id="ten_regression",
        name="Regression",
        created_at=created_at,
    ).public_dict()

    serialized = payload["created_at"]
    assert isinstance(serialized, str)
    assert serialized.endswith("Z")
    parsed = datetime.fromisoformat(serialized.replace("Z", "+00:00"))
    assert parsed.tzinfo == timezone.utc
    assert parsed.timestamp() == created_at
