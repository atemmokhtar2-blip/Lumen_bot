"""Sandbox process driver contract — engines/generators path removed."""
from pathlib import Path


def test_sandbox_driver_module_exists():
    from lumen.engine.services.live_deployment.sandbox_process_driver import (
        SandboxProcessDriver,
    )
    assert SandboxProcessDriver.name == "sandbox_runtime"


def test_state_store_schema_has_sandbox_backend():
    src = Path("lumen/engine/services/hosting/state_store.py").read_text()
    assert "sandbox_backend" in src
    src2 = Path("lumen/engine/services/hosting/pg_state_store.py").read_text()
    assert "sandbox_backend" in src2


def test_isolation_policy_imports_new_live_deployment_path():
    src = Path("lumen/engine/services/isolation_policy.py").read_text()
    assert "lumen.engine.services.live_deployment" in src
    assert "lumen.engine.engines.generators" not in src
