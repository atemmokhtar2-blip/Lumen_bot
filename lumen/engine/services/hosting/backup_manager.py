"""Compatibility shim — use ``lumen.hosting.backup_manager`` (canonical).

Do not add logic here. All implementations live under lumen.hosting.
"""
from lumen.hosting.backup_manager import *  # noqa: F403
