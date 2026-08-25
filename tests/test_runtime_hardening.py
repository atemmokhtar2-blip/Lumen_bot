"""Regression: stale singleton lock, durable paths, API fail-fast markers."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path


def test_stale_lock_reclaimed_when_pid_dead():
    import lumen.bot.singleton as sing

    sing._LOCK_FH = None
    root = tempfile.mkdtemp()
    os.environ["OUTPUT_DIR"] = root
    lock_path = Path(root) / ".lumen_bot.poll.lock"
    lock_path.write_text(f"999989\n{time.time()}\n")
    got = sing.acquire_bot_singleton(root, wait_seconds=5.0)
    assert got.exists()
    assert int(got.read_text().splitlines()[0]) == os.getpid()


def test_default_output_dir_not_tmp_generated():
    os.environ.pop("OUTPUT_DIR", None)
    os.environ.pop("STATE_DIR", None)
    os.environ.pop("DATA_DIR", None)
    import lumen.platform.paths as paths

    paths._RESOLVED = None
    d = paths.default_output_dir()
    assert "/tmp/generated" not in d
    assert "lumen" in d or ".runtime" in d or str(Path.home()) in d


def test_no_tmp_generated_defaults_in_source():
    root = Path(__file__).resolve().parents[1]
    bad = []
    for p in root.rglob("*.py"):
        if ".git" in p.parts or "__pycache__" in p.parts or "test" in p.as_posix():
            continue
        if p.name == "paths.py":
            continue
        if "/tmp/generated" in p.read_text(encoding="utf-8", errors="ignore"):
            bad.append(str(p.relative_to(root)))
    assert bad == [], bad


def test_api_fail_fast_markers_in_main():
    main = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "os._exit(1)" in main
    assert "sys.exit(1)" in main
    assert "api_death" in main
    assert "_watch_api_worker" in main
    assert "daemon=False" in main
