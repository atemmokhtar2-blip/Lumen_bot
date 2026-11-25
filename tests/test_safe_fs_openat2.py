"""Production path containment uses kernel-enforced openat2 resolution."""
from __future__ import annotations

import pytest


def test_openat2_write_and_read_nested_workspace_file(monkeypatch, tmp_path):
    from lumen.engine.services.linux_path_open import openat2_available
    if not openat2_available():
        pytest.skip("kernel does not expose openat2")

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("TBE_REQUIRE_OPENAT2", raising=False)
    root = tmp_path / "workspace"
    root.mkdir()

    from lumen.engine.services.safe_fs import safe_open_under, safe_write_text
    written = safe_write_text(root, "nested/deep/result.txt", "verified")
    assert written.read_text(encoding="utf-8") == "verified"

    with safe_open_under(root, "nested/deep/result.txt", "rb") as handle:
        assert handle.read() == b"verified"


def test_openat2_rejects_symlinked_parent_for_read_and_write(monkeypatch, tmp_path):
    from lumen.engine.services.linux_path_open import openat2_available
    if not openat2_available():
        pytest.skip("kernel does not expose openat2")

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("TBE_REQUIRE_OPENAT2", raising=False)
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (outside / "secret.txt").write_text("private", encoding="utf-8")
    (root / "escape").symlink_to(outside, target_is_directory=True)

    from lumen.engine.services.safe_fs import UnsafePathError, safe_open_under, safe_write_text
    with pytest.raises(UnsafePathError):
        safe_open_under(root, "escape/secret.txt", "rb")
    with pytest.raises(UnsafePathError):
        safe_write_text(root, "escape/created.txt", "must-not-escape")
    assert not (outside / "created.txt").exists()



def test_production_cannot_disable_openat2_with_environment_flag(monkeypatch):
    from lumen.engine.services.safe_fs import _require_openat2_for_paths

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("TBE_REQUIRE_OPENAT2", "0")
    assert _require_openat2_for_paths() is True

    monkeypatch.setenv("ENVIRONMENT", "test")
    assert _require_openat2_for_paths() is False
