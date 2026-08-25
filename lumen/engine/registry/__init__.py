"""
Registry package — discovery and registration of engine components.

The registry is the central place where engines, builders, and
validators announce themselves.  The pipeline orchestrator queries the
registry to obtain the components it needs for each stage.
"""

from .registry import EngineRegistry, RegistryEntry

__all__ = ["EngineRegistry", "RegistryEntry"]
