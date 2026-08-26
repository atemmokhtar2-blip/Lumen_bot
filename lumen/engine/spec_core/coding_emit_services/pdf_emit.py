
"""Emit PDF images→PDF service from runtime module."""
from __future__ import annotations
from pathlib import Path

def _emit_pdf_service() -> str:
    path = Path(__file__).resolve().parents[1] / "runtime" / "pdf_runtime.py"
    if path.is_file():
        return path.read_text(encoding="utf-8")
    raise FileNotFoundError(f"pdf_runtime missing: {path}")
