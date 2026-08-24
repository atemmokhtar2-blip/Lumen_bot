"""Self-expanding macro registry — successful DynamicBotSpecs become reusable macros."""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .infinite_schema import DynamicBotSpec
from .ast_validator import validate_dynamic_spec

logger = logging.getLogger(__name__)


class MacroRegistry:
    def __init__(self, root: Path | None = None) -> None:
        base = Path(
            root
            or os.environ.get("TBE_MACRO_REGISTRY_DIR")
            or (Path(os.environ.get("OUTPUT_DIR") or (Path.home() / ".capability_maestro")) / "macro_registry")
        )
        self.root = base
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._index = self.root / "index.json"

    def _load_index(self) -> dict[str, Any]:
        if not self._index.exists():
            return {"macros": {}}
        try:
            return json.loads(self._index.read_text(encoding="utf-8") or "{}")
        except Exception:
            return {"macros": {}}

    def _save_index(self, data: dict[str, Any]) -> None:
        self._index.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def promote(
        self,
        spec: DynamicBotSpec | dict[str, Any],
        *,
        macro_id: str | None = None,
        score: float = 1.0,
    ) -> str:
        """Save a validated successful spec as a composite macro."""
        dyn = validate_dynamic_spec(spec)
        mid = (macro_id or dyn.bot_name or "macro").strip().lower().replace(" ", "_")[:64]
        mid = "".join(c for c in mid if c.isalnum() or c in "_-") or f"macro_{int(time.time())}"
        path = self.root / f"{mid}.json"
        with self._lock:
            path.write_text(
                json.dumps(dyn.model_dump(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            idx = self._load_index()
            macros = dict(idx.get("macros") or {})
            prev = dict(macros.get(mid) or {})
            macros[mid] = {
                "id": mid,
                "bot_name": dyn.bot_name,
                "uses": int(prev.get("uses") or 0) + 1,
                "score": max(float(prev.get("score") or 0), float(score)),
                "nodes": len(dyn.nodes),
                "updated_at": time.time(),
            }
            idx["macros"] = macros
            self._save_index(idx)
        logger.info("macro promoted id=%s nodes=%s", mid, len(dyn.nodes))
        return mid

    def get(self, macro_id: str) -> Optional[DynamicBotSpec]:
        path = self.root / f"{macro_id}.json"
        if not path.exists():
            return None
        try:
            return validate_dynamic_spec(json.loads(path.read_text(encoding="utf-8")))
        except Exception:
            return None

    def list_macros(self, *, limit: int = 50) -> list[dict[str, Any]]:
        with self._lock:
            idx = self._load_index()
            items = list((idx.get("macros") or {}).values())
        items.sort(key=lambda m: (float(m.get("score") or 0), float(m.get("uses") or 0)), reverse=True)
        return items[:limit]


_REG: MacroRegistry | None = None
_LOCK = threading.Lock()


def get_macro_registry() -> MacroRegistry:
    global _REG
    with _LOCK:
        if _REG is None:
            _REG = MacroRegistry()
        return _REG
