"""MMDS + honest guest status markers."""
from pathlib import Path


def test_configure_vm_has_mmds():
    src = Path("lumen/engine/services/sandbox_runtime/firecracker_backend.py").read_text()
    assert "/mmds" in src
    assert "TBE_FC_MMDS" in src
    assert "mmds_payload" in src


def test_status_uses_guest_markers():
    src = Path("lumen/engine/services/sandbox_runtime/firecracker_backend.py").read_text()
    assert "lumen-guest-ready" in src
    assert "vm_process_alive_guest_unconfirmed" in src
    assert "_guest_log_markers" in src


def test_guest_init_has_mmds_and_markers():
    src = Path("scripts/hosting/build_fc_rootfs.sh").read_text()
    assert "lumen-guest-ready" in src
    assert "169.254.169.254" in src
    assert "lumen-bot-started" in src
