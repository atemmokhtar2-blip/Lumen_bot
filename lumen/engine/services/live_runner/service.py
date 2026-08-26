"""
LiveRunner — real dependency install + bot process execution + error capture.

Install strategy (robust):
  1) try venv + ensure pip works
  2) if venv/pip broken → pip install --target .tbe_deps (isolated)
  3) surface real pip ERROR lines to the user (no opaque "pip install failed")
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import ast



from .parts.report import *
from .parts.telegram_api import *
from .parts.runtime_bootstrap import *
from .parts.requirements_pip import *
from .parts.project_patch import *
from .parts.runner import *


# Explicit re-exports (import * skips leading-underscore names)
from .parts.runtime_bootstrap import (
    _ensure_runtime,
    _find_requirements,
    _find_entry,
    _venv_python,
    _deps_dir,
)
from .parts.requirements_pip import (
    _pip_install,
    _preflight_ensure_deps,
    _sanitize_requirements,
    _extract_errors,
    _extract_missing_modules,
    _ensure_packages_in_requirements,
    _pip_install_packages_direct,
    _module_to_package,
)

__all__ = [
    "LiveRunReport",
    "validate_telegram_token",
    "LiveRunnerService",
    "run_bot_project",
]
