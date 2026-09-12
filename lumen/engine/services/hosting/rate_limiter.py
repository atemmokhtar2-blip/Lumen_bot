"""Compatibility shim — use ``lumen.hosting.rate_limiter`` (canonical).

Do not add logic here. All implementations live under lumen.hosting.
"""
from lumen.hosting.rate_limiter import *  # noqa: F403
