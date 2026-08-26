"""Quality gate: real hybrid retrieval + repo_context must work on a sample tree.

This is not a full generation bench — it fails CI if code-intel path is broken/fake.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any


def run_code_intel_gate() -> dict[str, Any]:
    """Build a small multi-file tree and require hybrid hits + context pack."""
    with tempfile.TemporaryDirectory(prefix="lumen_ci_") as td:
        root = Path(td)
        (root / "main.py").write_text(
            "def main():\n    from handlers import on_start\n    on_start()\n",
            encoding="utf-8",
        )
        (root / "handlers.py").write_text(
            "def on_start():\n    return \"hello\"\n\ndef on_help():\n    return \"help\"\n",
            encoding="utf-8",
        )
        (root / "utils.py").write_text(
            "def format_msg(x):\n    return str(x)\n",
            encoding="utf-8",
        )
        from lumen.engine.services.code_intelligence.hybrid_retrieval import hybrid_search
        from lumen.engine.services.code_intelligence.repo_context import pack_repo_context_for_goal

        hs = hybrid_search(root, "on_start handler telegram", top_k=5)
        hits = list(hs.get("hits") or [])
        paths = {str(h.get("path") or "") for h in hits if isinstance(h, dict)}
        pack = pack_repo_context_for_goal(root, "fix on_start handler", extra_paths=["handlers.py"])
        files = pack.get("files") or {}
        ok = bool(hits) and bool(files) and (
            "handlers.py" in paths or "handlers.py" in files or "main.py" in files
        )
        return {
            "ok": ok,
            "hybrid_hits": len(hits),
            "embed_provider": hs.get("embed_provider"),
            "engine": hs.get("engine"),
            "pack_files": list(files.keys()),
            "pack_ok": bool(pack.get("ok")),
            "errors": [] if ok else ["code_intel_gate_failed"],
        }


def main() -> int:
    import json
    import sys
    r = run_code_intel_gate()
    print(json.dumps(r, indent=2, ensure_ascii=False))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
