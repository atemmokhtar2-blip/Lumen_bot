"""Guest-side supervisor assets injected into permanent-host project drives."""
from __future__ import annotations

from pathlib import Path

AGENT_DIR = Path(__file__).resolve().parent
SUPERVISOR_PATH = AGENT_DIR / "supervisor.py"
BOOT_SH_PATH = AGENT_DIR / "lumen-guest-boot.sh"
