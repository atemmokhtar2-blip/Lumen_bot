from __future__ import annotations

import pytest

from lumen.engine.services.live_deployment import docker_process_driver as driver
from lumen.engine.services.sandbox_runtime.network import ensure_egress_network


def test_runtime_is_allowlisted(monkeypatch):
    monkeypatch.delenv("TBE_DOCKER_RUNTIME", raising=False)
    assert driver._runtime_args() == []

    monkeypatch.setenv("TBE_DOCKER_RUNTIME", "runsc")
    assert driver._runtime_args() == ["--runtime", "runsc"]

    monkeypatch.setenv("TBE_DOCKER_RUNTIME", "--privileged")
    with pytest.raises(ValueError, match="unsupported_docker_runtime"):
        driver._runtime_args()


def test_apparmor_profile_rejects_option_injection(monkeypatch):
    monkeypatch.setenv("TBE_APPARMOR_PROFILE", "safe-profile;--privileged")
    with pytest.raises(ValueError, match="invalid_apparmor_profile"):
        driver._apparmor_args()


def test_resource_limits_are_bounded(monkeypatch):
    monkeypatch.setattr(driver, "_MEMORY", "192m")
    monkeypatch.setattr(driver, "_CPUS", "0.4")
    monkeypatch.setattr(driver, "_PIDS", "48")
    assert driver._resource_args() == [
        "--memory=192m",
        "--memory-swap=192m",
        "--cpus=0.4",
        "--pids-limit=48",
    ]

    monkeypatch.setattr(driver, "_MEMORY", "2g")
    with pytest.raises(ValueError, match="docker_memory_limit_out_of_range"):
        driver._resource_args()


def test_network_name_rejects_docker_flag_injection(monkeypatch):
    monkeypatch.setenv("TBE_DOCKER_NETWORK", "--privileged")
    with pytest.raises(RuntimeError, match="invalid_docker_network_name"):
        ensure_egress_network(create_if_missing=False)
