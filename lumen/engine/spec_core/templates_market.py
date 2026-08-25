"""Compatibility facade for the market runtime template."""
from .runtime import market_runtime as _runtime

# Preserve the complete historical module surface for existing imports.
globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})
