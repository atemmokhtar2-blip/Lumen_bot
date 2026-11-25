"""Prometheus middleware registration must be safe across app factories."""
from __future__ import annotations

import pytest


def test_metrics_middleware_registration_is_idempotent():
    pytest.importorskip("prometheus_client")
    from lumen.platform.observability.metrics_http import instrument_app_middleware

    first = instrument_app_middleware()
    second = instrument_app_middleware()
    assert callable(first)
    assert callable(second)
