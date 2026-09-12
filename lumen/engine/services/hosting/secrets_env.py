"""Compatibility shim — use ``lumen.hosting.secrets_env`` (canonical).

Do not add logic here. All implementations live under lumen.hosting.
"""
from lumen.hosting.secrets_env import *  # noqa: F403
