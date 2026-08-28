"""User-facing errors must not leak paths; fallback workdir is restricted."""
from __future__ import annotations

from pathlib import Path

from lumen.bot.sanitize import user_facing_generation_error
from lumen.bot.safe_workdir import allocate_fallback_workdir


def test_user_facing_error_hides_paths():
    msg = user_facing_generation_error(FileNotFoundError("/etc/passwd"))
    assert "/etc/passwd" not in msg
    assert "missing_resource" in msg


def test_user_facing_error_generic_code():
    msg = user_facing_generation_error(code="generation_failed")
    assert "generation_failed" in msg


def test_fallback_workdir_under_tmp_lumen():
    p = allocate_fallback_workdir(7)
    assert p.is_dir()
    assert "/tmp/lumen_fallback" in str(p.resolve())
    # not host root
    assert p.resolve() != Path("/")
