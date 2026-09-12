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
    offenders = []
    for p in _iter_py(LUMEN / "platform"):
        src = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"from lumen\.bot\b|import lumen\.bot\b", src):
            offenders.append(str(p.relative_to(ROOT)))
    assert not offenders, f"platform→bot imports forbidden: {offenders}"


def test_hosting_does_not_import_bot():
    """New hosting→bot imports are banned; allowlist is known debt only."""
    allow = {
        "lumen/hosting/project_manifest.py",
        "lumen/hosting/rate_limiter.py",
        "lumen/hosting/serverless_policy.py",
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
