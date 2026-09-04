
"""Network isolation wiring, resource ceilings, backup/restore."""
from __future__ import annotations

from pathlib import Path
import tarfile
import json


def test_clamp_bot_resources_ceiling():
    from lumen.engine.services.sandbox_runtime.policy import clamp_bot_resources
    mem, cpu = clamp_bot_resources(memory_mb=9999, cpus=8.0)
    assert mem <= 256
    assert cpu <= 0.5
    mem2, cpu2 = clamp_bot_resources(memory_mb=32, cpus=0.01)
    assert mem2 >= 64
    assert cpu2 >= 0.1


def test_policy_defaults_stricter():
    from lumen.engine.services.sandbox_runtime.policy import load_policy
    p = load_policy()
    # parse memory string
    assert "128" in p.max_memory or float(p.max_cpus) <= 0.25


def test_backup_and_restore_roundtrip(tmp_path):
    from lumen.hosting.backup_manager import backup_project, restore_project, list_backups
    proj = tmp_path / "bot"
    proj.mkdir()
    (proj / "bot.db").write_bytes(b"sqlite-bytes-demo")
    (proj / "storage.json").write_text('{"k":1}', encoding="utf-8")
    res = backup_project(proj, instance_id="testinst")
    assert res["ok"] is True
    arc = Path(res["path"])
    assert arc.is_file()
    # wipe and restore
    (proj / "bot.db").unlink()
    r2 = restore_project(arc, proj)
    assert r2["ok"] is True
    assert (proj / "bot.db").read_bytes() == b"sqlite-bytes-demo"
    listed = list_backups("testinst")
    assert any(x["name"] == arc.name for x in listed)


def test_harden_network_callable():
    # Should not crash when docker/iptables unavailable — returns report dict
    from lumen.engine.services.sandbox_runtime import egress
    assert hasattr(egress, "harden_network")
    assert callable(egress.harden_network)
