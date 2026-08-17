"""Zero-AI presets: map plain-language requests to BotSpec packs.

Used when the user asks for a common bot type (e.g. group management)
without going through the button builder or any LLM.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

from .acceptance_packs import tests_for_preset
from .builder import BuilderSession
from .schema import BotSpec
from .seed_packs import seed_for_preset


