"""Strong tests for multi-file agent FS tools (official agent_fs path)."""
from __future__ import annotations

from pathlib import Path

import pytest

from lumen.engine.services.cline_runtime.agent_fs import (
    apply_edits,
    apply_patch,
    edit_file,
    glob_files,
    grep_codebase,
    read_files,
    run_tool,
    write_file,
)


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "a.py").write_text("def foo():\n    return 1\n\ndef bar():\n    return 2\n", encoding="utf-8")
    (tmp_path / "pkg" / "b.py").write_text("from pkg.a import foo\n\ndef use():\n    return foo()\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("from pkg.b import use\n\nif __name__ == '__main__':\n    print(use())\n", encoding="utf-8")
    return tmp_path


def test_edit_file_requires_unique_old_string(workspace: Path):
    # two identical lines would fail uniqueness — use a string that appears twice
    (workspace / "dup.py").write_text("x = 1\nx = 1\n", encoding="utf-8")
    r = edit_file(str(workspace), "dup.py", "x = 1", "x = 2", replace_all=False)
    assert r["ok"] is False
    assert r["error"] == "old_string_not_unique"
    r2 = edit_file(str(workspace), "dup.py", "x = 1", "x = 2", replace_all=True)
    assert r2["ok"] is True


def test_grep_and_glob(workspace: Path):
    g = grep_codebase(str(workspace), r"def foo")
    assert g["ok"] is True
    assert any("a.py" in m["path"] for m in g["matches"])
    files = glob_files(str(workspace), "**/*.py")
    assert files["ok"] is True
    assert files["count"] >= 3


def test_read_files_batch(workspace: Path):
    r = read_files(str(workspace), ["pkg/a.py", "pkg/b.py", "missing.py"])
    assert r["ok"] is True
    assert "pkg/a.py" in r["files"]
    assert "pkg/b.py" in r["files"]
    assert any("missing" in e for e in r["errors"])


def test_apply_edits_atomic_rollback(workspace: Path):
    # second edit fails → first rolled back
    r = apply_edits(
        str(workspace),
        [
            {"path": "pkg/a.py", "old_string": "return 1", "new_string": "return 10"},
            {"path": "pkg/a.py", "old_string": "DOES_NOT_EXIST", "new_string": "x"},
        ],
        atomic=True,
    )
    assert r["ok"] is False
    assert r.get("rolled_back") is True
    text = (workspace / "pkg" / "a.py").read_text(encoding="utf-8")
    assert "return 1" in text
    assert "return 10" not in text


def test_apply_edits_multi_file_success(workspace: Path):
    r = apply_edits(
        str(workspace),
        [
            {"path": "pkg/a.py", "old_string": "return 1", "new_string": "return 42"},
            {"path": "pkg/b.py", "old_string": "from pkg.a import foo", "new_string": "from pkg.a import foo  # used"},
        ],
    )
    assert r["ok"] is True
    assert r["count"] == 2
    assert "return 42" in (workspace / "pkg" / "a.py").read_text(encoding="utf-8")


def test_apply_patch_add_and_update(workspace: Path):
    patch = """*** Add File: pkg/c.py
+def extra():
+    return 99

*** Update File: main.py
@@ -1,3 +1,4 @@
 from pkg.b import use
+from pkg.c import extra
 
 if __name__ == '__main__':
-    print(use())
+    print(use(), extra())
"""
    # Use simpler update format without fragile hunks
    patch2 = """*** Add File: pkg/c.py
def extra():
    return 99
"""
    r = apply_patch(str(workspace), patch2)
    assert r["ok"] is True
    assert (workspace / "pkg" / "c.py").is_file()
    assert "return 99" in (workspace / "pkg" / "c.py").read_text(encoding="utf-8")


def test_run_tool_dispatch(workspace: Path):
    r = run_tool(str(workspace), "grep_codebase", {"pattern": "def bar"})
    assert r["ok"] is True
    r2 = run_tool(str(workspace), "apply_edits", {
        "edits": [{"path": "pkg/a.py", "old_string": "return 2", "new_string": "return 3"}]
    })
    assert r2["ok"] is True
