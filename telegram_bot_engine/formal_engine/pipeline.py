"""
End-to-end Formal Pipeline.

Text → Deep Understanding → FormalBotSpec → Clean Project
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from .understanding.requirement_extractor import extract_formal_spec
from .generation.project_generator import generate_project
from .schemas.formal_spec import FormalBotSpec

logger = logging.getLogger(__name__)


def run_pipeline(user_text: str, output_dir: str | Path) -> tuple[FormalBotSpec, Path, float]:
    """
    Full deterministic pipeline.

    Returns:
        (spec, project_path, total_seconds)
    """
    t0 = time.perf_counter()

    # 1. Extreme-precision understanding
    spec = extract_formal_spec(user_text)
    t_understand = time.perf_counter() - t0

    # 2. Deterministic clean code generation
    t1 = time.perf_counter()
    project_path = generate_project(spec, output_dir)
    t_generate = time.perf_counter() - t1

    total = time.perf_counter() - t0
    logger.info(
        "Pipeline finished: understand=%.1fms generate=%.1fms total=%.1fms → %s",
        t_understand * 1000,
        t_generate * 1000,
        total * 1000,
        project_path,
    )
    return spec, project_path, total
