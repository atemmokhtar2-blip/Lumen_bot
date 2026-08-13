"""
Base engine helpers — shared implementation for all engines.

* :class:`BaseEngine` — convenience base for engines that return a
  :class:`StageResult` and want consistent logging.
* :class:`BaseGenerator` — convenience base for generator engines that
  rely on builders to materialise files.
"""

from .base_engine import BaseEngine
from .base_generator import BaseGenerator

__all__ = ["BaseEngine", "BaseGenerator"]
