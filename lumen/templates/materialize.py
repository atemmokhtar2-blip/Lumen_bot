"""Materialize a template asset tree into the user sandbox (Phase 3).

No lumen.bot imports — keeps templates bounded context free of Telegram UI.
"""
from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path

from lumen.templates.catalog import get_template
from lumen.templates.errors import CatalogError, TemplatesError

logger = logging.getLogger(__name__)

_ASSETS = Path(__file__).resolve().parent / "assets"


class MaterializeError(TemplatesError):
    code = "materialize_error"


def _output_root() -> Path:
    return Path(
        os.getenv("OUTPUT_DIR")
        or os.getenv("LUMEN_OUTPUT_DIR")
        or os.getenv("TBE_OUTPUT_DIR")
        or "/tmp/lumen_output"
    )


def asset_dir_for(template_id: str) -> Path:
    spec = get_template(template_id)
    if spec is None:
        raise CatalogError(f"template_not_found:{template_id}")
    key = (spec.asset_key or spec.id).strip()
    root = (_ASSETS / key).resolve()
    assets_root = _ASSETS.resolve()
    if not str(root).startswith(str(assets_root)):
        raise MaterializeError("asset_path_escape")
    if not root.is_dir() or not (root / "main.py").is_file():
        raise MaterializeError(f"asset_missing:{key}")
    return root


def materialize_to_sandbox(user_id: int, template_id: str) -> Path:
    """Copy template files into a new sandbox project dir. Returns project root."""
    uid = int(user_id or 0)
    if uid <= 0:
        raise MaterializeError("invalid_user_id")
    src = asset_dir_for(template_id)
    out_root = _output_root()

    try:
        from lumen.engine.services.user_sandbox import get_user_sandbox

        dest = get_user_sandbox(uid, out_root).new_project_dir(label="tpl")
    except Exception as exc:
        # Fallback: deterministic path under output root (still per-user)
        dest = out_root / "users" / str(uid) / "templates" / f"tpl_{template_id}"
        try:
            dest.mkdir(parents=True, exist_ok=True)
        except Exception as exc2:
            raise MaterializeError(f"sandbox_alloc_failed:{type(exc).__name__}") from exc2
        logger.warning(
            "user_sandbox unavailable (%s) — fallback %s", type(exc).__name__, dest
        )

    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        if item.name.startswith("."):
            continue
        target = dest / item.name
        if item.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(item, target)
        else:
            shutil.copy2(item, target)
    if not (dest / "main.py").is_file():
        raise MaterializeError("materialize_incomplete")
    logger.info("template materialized uid=%s template=%s path=%s", uid, template_id, dest)
    return dest.resolve()


__all__ = ["MaterializeError", "asset_dir_for", "materialize_to_sandbox"]
