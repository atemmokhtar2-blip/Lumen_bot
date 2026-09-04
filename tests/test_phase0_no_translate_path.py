"""Phase 0 acceptance: no translate_request / gate_llm_call on generation path."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = (
    "translate_request",
    "chat_request",
    "gate_llm_call",
    "llm_budget_gate",
)


def test_no_forbidden_symbols_in_agent_generation_path():
    roots = [
        ROOT / "lumen/engine/services/cline_runtime",
        ROOT / "lumen/engine/brain",
        ROOT / "lumen/engine/turn",
        ROOT / "lumen/engine/services/llm",
        ROOT / "lumen/bot/routers",
    ]
    hits: list[str] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in str(path):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for needle in FORBIDDEN:
                if needle in text:
                    # allow comments that say "removed" only if def not present
                    for i, line in enumerate(text.splitlines(), 1):
                        if needle in line and not line.strip().startswith("#"):
                            if f"def {needle}" in line or f"import {needle}" in line or f"{needle}(" in line:
                                hits.append(f"{path.relative_to(ROOT)}:{i}:{line.strip()[:80]}")
    assert not hits, "forbidden generation-path symbols:\n" + "\n".join(hits)


def test_no_facade_or_budget_files():
    assert not (ROOT / "lumen/engine/services/llm/facade.py").exists()
    assert not (ROOT / "lumen/engine/services/llm_budget_gate.py").exists()
    assert not (ROOT / "lumen/llm/facade.py").exists()
