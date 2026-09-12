"""Executable architecture — prevent logic drift and forbidden dependency edges.

2025–2026 practice: architecture as tests (Import Linter / pytest-archon style).
Shared kernel: lumen.platform (envutil, token_patterns, project_paths, paths).
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LUMEN = ROOT / "lumen"


def _iter_py(base: Path):
    for p in base.rglob("*.py"):
        yield p


def _parse(path: Path):
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="ignore"))
    except SyntaxError:
        return None


def test_no_redefined_looks_like_bot_token_logic():
    offenders = []
    for p in _iter_py(LUMEN):
        if p.as_posix().endswith("platform/token_patterns.py"):
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        if "def looks_like_bot_token" not in src:
            continue
        tree = _parse(p)
        if tree is None:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "looks_like_bot_token":
                body_src = ast.get_source_segment(src, node) or ""
                if "token_patterns" in body_src or "message_classify" in body_src:
                    continue
                if "re.match" in body_src or "_TOKEN_RE" in body_src or "_BOT_RE" in body_src:
                    offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, f"duplicate bot-token logic in: {offenders}"


def test_no_local_flag_reimplementation():
    offenders = []
    for p in _iter_py(LUMEN):
        if p.as_posix().endswith("platform/envutil.py"):
            continue
        src = p.read_text(encoding="utf-8", errors="ignore")
        if "def _flag(" not in src:
            continue
        if "envutil import" in src and "as _flag" in src:
            continue
        tree = _parse(p)
        if tree is None:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "_flag":
                body_src = ast.get_source_segment(src, node) or ""
                if "environ.get" in body_src and "true" in body_src.lower():
                    offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, f"local _flag reimplementation in: {offenders}"


def test_platform_does_not_import_bot():
    """platform is shared kernel; only subscription_store may soft-import bot session cache."""
    allow = {
        "lumen/platform/subscription_store.py",  # session cache + facts invalidate (debt)
    }
    offenders = []
    for p in _iter_py(LUMEN / "platform"):
        src = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"from lumen\.bot\b|import lumen\.bot\b", src):
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            if rel not in allow:
                offenders.append(rel)
    assert not offenders, f"platform→bot imports forbidden: {offenders}"


def test_hosting_does_not_import_bot():
    """New hosting→bot imports are banned; allowlist is known debt only."""
    allow = {
        # plan limits moved to platform.entitlement — only webhook still touches bot
        "lumen/hosting/webhook_manager.py",
    }
    offenders = []
    for p in _iter_py(LUMEN / "hosting"):
        src = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"from lumen\.bot\b|import lumen\.bot\b", src):
            rel = str(p.relative_to(ROOT)).replace("\\", "/")
            if rel not in allow:
                offenders.append(rel)
    assert not offenders, f"hosting→bot imports forbidden (new): {offenders}"


def test_shared_kernel_modules_exist():
    assert (LUMEN / "platform" / "envutil.py").is_file()
    assert (LUMEN / "platform" / "token_patterns.py").is_file()
    assert (LUMEN / "platform" / "project_paths.py").is_file()
    assert (LUMEN / "platform" / "paths.py").is_file()


def test_plan_limits_imported_from_platform():
    """Hosting/engine must not import plan limits from bot.ui."""
    offenders = []
    for base in (LUMEN / "hosting", LUMEN / "engine"):
        for p in _iter_py(base):
            src = p.read_text(encoding="utf-8", errors="ignore")
            if "lumen.bot.ui.pro_plan_entitlement" in src:
                offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, f"plan limits must come from platform.entitlement: {offenders}"


def test_entry_point_single_module():
    """Drivers must not redefine _find_entry_point body."""
    offenders = []
    for name in ("local_process_driver.py", "docker_process_driver.py"):
        p = LUMEN / "engine" / "services" / "live_deployment" / name
        src = p.read_text(encoding="utf-8", errors="ignore")
        tree = _parse(p)
        if tree is None:
            continue
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name == "_find_entry_point":
                body = ast.get_source_segment(src, node) or ""
                if "main.py" in body and "bot.py" in body:
                    offenders.append(name)
    assert not offenders, f"duplicate entry-point discovery: {offenders}"
