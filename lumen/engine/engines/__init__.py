"""
Engines package — all generation engines.

This package contains two sub-packages:

* :mod:`base` — shared helpers for building engines.
* :mod:`generators` — concrete generator engines.

Engines are discovered and registered at startup; the pipeline never
imports them directly.
"""

from .base.base_engine import BaseEngine
from .base.base_generator import BaseGenerator

__all__ = ["BaseEngine", "BaseGenerator"]
