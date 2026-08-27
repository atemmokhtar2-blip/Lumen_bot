from pathlib import Path

def test_live_engine_uses_sandbox_driver():
    src = Path("lumen/engine/engines/generators/live_deployment/live_deployment_engine.py").read_text()
    assert "SandboxProcessDriver" in src
    assert "select_process_driver" not in src

def test_sandbox_driver_module_exists():
    from lumen.engine.engines.generators.live_deployment.sandbox_process_driver import (
        SandboxProcessDriver,
    )
    assert SandboxProcessDriver.name == "sandbox_runtime"

def test_state_store_schema_has_sandbox_backend():
    src = Path("lumen/engine/services/hosting/state_store.py").read_text()
    assert "sandbox_backend" in src
    src2 = Path("lumen/engine/services/hosting/pg_state_store.py").read_text()
    assert "sandbox_backend" in src2
