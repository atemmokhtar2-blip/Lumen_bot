"""Generic capability runtime — deep durable SQLite for any service.method.

Copied into generated projects as app/services/generic.py.
"""
from __future__ import annotations

import ast
import json
import operator
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db import connect, init_db


