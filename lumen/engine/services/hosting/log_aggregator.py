"""Compatibility shim — use ``lumen.hosting.log_aggregator`` (canonical).

Do not add logic here. All implementations live under lumen.hosting.
"""
from lumen.hosting.log_aggregator import *  # noqa: F403
