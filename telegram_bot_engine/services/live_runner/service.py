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

__all__ = [
    "LiveRunReport",
    "validate_telegram_token",
    "LiveRunnerService",
    "run_bot_project",
]
