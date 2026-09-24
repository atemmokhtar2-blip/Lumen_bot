"""LanguageRuntime — first-class language model for multi-runtime Lumen (2026).

Phase 1 (foundation):
  - Formal LanguageRuntime enum + capability matrix (language × ProjectKind)
  - resolve_language() from user text / explicit package field
  - RuntimeRecipe: container image, install, start, health (OCI-oriented)
  - is_language_enabled() — default python only; expand via LUMEN_ENABLED_LANGUAGES
  - Wired into BuildIR.language + metadata (same path as project_kind)

Strong 2026 practice:
  - Explicit allowlist (not "any language")
  - Recipe per language for future Docker/Firecracker workers
  - Detection confidence + notes for audit
  - Capability matrix: which (language, kind) pairs the platform claims
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any


class LanguageRuntime(str, Enum):
    PYTHON = "python"
    NODE = "node"           # JavaScript / Node.js
    TYPESCRIPT = "typescript"
    GO = "go"
    RUST = "rust"
    # Future: JAVA, DOTNET, RUBY, PHP — add only with recipe + acceptance


@dataclass(frozen=True)
class RuntimeRecipe:
    """How to install and start a project of this language (VPS / local)."""
    language: LanguageRuntime
    docker_image: str
    package_manager: str
    install_command: str
    default_start: str
    health_hint: str
    source_globs: tuple[str, ...]
    manifest_files: tuple[str, ...]


_RECIPES: dict[LanguageRuntime, RuntimeRecipe] = {
    LanguageRuntime.PYTHON: RuntimeRecipe(
        language=LanguageRuntime.PYTHON,
        docker_image="python:3.12-slim",
        package_manager="pip",
        install_command="pip install -q -r requirements.txt",
        default_start="uvicorn main:app --host 127.0.0.1 --port $PORT",
        health_hint="/health",
        source_globs=("*.py",),
        manifest_files=("requirements.txt", "pyproject.toml", "Pipfile"),
    ),
    LanguageRuntime.NODE: RuntimeRecipe(
        language=LanguageRuntime.NODE,
        docker_image="node:22-slim",
        package_manager="npm",
        install_command="npm ci --omit=dev || npm install --omit=dev",
        default_start="node dist/index.js || node src/index.js || node index.js",
        health_hint="/health",
        source_globs=("*.js", "*.mjs", "*.cjs"),
        manifest_files=("package.json",),
    ),
    LanguageRuntime.TYPESCRIPT: RuntimeRecipe(
        language=LanguageRuntime.TYPESCRIPT,
        docker_image="node:22-slim",
        package_manager="npm",
        install_command="npm ci && npx tsc -p tsconfig.json --pretty false",
        default_start="node dist/index.js",
        health_hint="/health",
        source_globs=("*.ts", "*.tsx"),
        manifest_files=("package.json", "tsconfig.json"),
    ),
    LanguageRuntime.GO: RuntimeRecipe(
        language=LanguageRuntime.GO,
        docker_image="golang:1.23-alpine",
        package_manager="go",
        install_command="go mod download",
        default_start="./app",
        health_hint="/health",
        source_globs=("*.go",),
        manifest_files=("go.mod",),
    ),
    LanguageRuntime.RUST: RuntimeRecipe(
        language=LanguageRuntime.RUST,
        docker_image="rust:1.83-slim",
        package_manager="cargo",
        install_command="cargo build --release",
        default_start="./target/release/app",
        health_hint="/health",
        source_globs=("*.rs",),
        manifest_files=("Cargo.toml",),
    ),
}


# (language, kind) pairs the platform intends to support when language is enabled
_CAPABILITY_MATRIX: dict[LanguageRuntime, frozenset[str]] = {
    LanguageRuntime.PYTHON: frozenset({
        "telegram_bot", "web_site", "web_api", "cli_app", "library",
        "discord_bot", "whatsapp_bot", "general_app", "refine",
    }),
    LanguageRuntime.NODE: frozenset({"web_api", "web_site", "cli_app", "general_app"}),
    LanguageRuntime.TYPESCRIPT: frozenset({"web_api", "web_site", "cli_app", "general_app"}),
    LanguageRuntime.GO: frozenset({"web_api", "cli_app", "library", "general_app"}),
    LanguageRuntime.RUST: frozenset({"web_api", "cli_app", "library", "general_app"}),
}


_LABEL_AR: dict[LanguageRuntime, str] = {
    LanguageRuntime.PYTHON: "بايثون",
    LanguageRuntime.NODE: "Node.js",
    LanguageRuntime.TYPESCRIPT: "TypeScript",
    LanguageRuntime.GO: "Go",
    LanguageRuntime.RUST: "Rust",
}


# Detection patterns (order matters — more specific first)
_DETECT: list[tuple[LanguageRuntime, re.Pattern[str], float]] = [
    (LanguageRuntime.TYPESCRIPT, re.compile(
        r"(?i)\b(typescript|\.tsx?\b|ts-node|tsc\b|nestjs|express\s*\+\s*ts)\b",
    ), 0.92),
    (LanguageRuntime.NODE, re.compile(
        r"(?i)\b(node\.?js|nodejs|npm\b|express(?!\s*\+\s*ts)|fastify|nest(?!js)|javascript|\.jsx?\b)\b",
    ), 0.88),
    (LanguageRuntime.GO, re.compile(
        r"(?i)(\bgolang\b|\bin\s+go\b|\bgo\s+(api|service|server|with|module)\b|\bgin\b|\becho\s+framework\b|\bfiber\b)",
    ), 0.90),
    (LanguageRuntime.RUST, re.compile(
        r"(?i)\b(rust\b|cargo\b|actix|axum|rocket\.rs)\b",
    ), 0.90),
    (LanguageRuntime.PYTHON, re.compile(
        r"(?i)\b(python|fastapi|flask|django|uvicorn|aiogram|python-telegram|ptb|django)\b",
    ), 0.85),
]


def parse_language(raw: Any) -> LanguageRuntime | None:
    s = str(raw or "").strip().lower().replace(" ", "")
    if not s:
        return None
    aliases = {
        "py": LanguageRuntime.PYTHON,
        "python3": LanguageRuntime.PYTHON,
        "python": LanguageRuntime.PYTHON,
        "js": LanguageRuntime.NODE,
        "javascript": LanguageRuntime.NODE,
        "node": LanguageRuntime.NODE,
        "nodejs": LanguageRuntime.NODE,
        "ts": LanguageRuntime.TYPESCRIPT,
        "typescript": LanguageRuntime.TYPESCRIPT,
        "go": LanguageRuntime.GO,
        "golang": LanguageRuntime.GO,
        "rust": LanguageRuntime.RUST,
        "rs": LanguageRuntime.RUST,
    }
    if s in aliases:
        return aliases[s]
    try:
        return LanguageRuntime(s)
    except ValueError:
        return None


def enabled_languages() -> frozenset[LanguageRuntime]:
    """Default: python only. Expand: LUMEN_ENABLED_LANGUAGES=python,node,typescript,go"""
    raw = (os.environ.get("LUMEN_ENABLED_LANGUAGES") or "python").strip().lower()
    out: set[LanguageRuntime] = set()
    for part in re.split(r"[,;\s]+", raw):
        lang = parse_language(part)
        if lang is not None:
            out.add(lang)
    if not out:
        out.add(LanguageRuntime.PYTHON)
    return frozenset(out)


def is_language_enabled(lang: LanguageRuntime | str | None) -> bool:
    if lang is None:
        return True  # default path → python later
    lr = parse_language(lang) if not isinstance(lang, LanguageRuntime) else lang
    if lr is None:
        return False
    return lr in enabled_languages()


def kind_supported_for_language(kind: str, lang: LanguageRuntime) -> bool:
    allowed = _CAPABILITY_MATRIX.get(lang) or frozenset()
    return (kind or "").strip().lower() in allowed


def recipe_for(lang: LanguageRuntime | str | None) -> RuntimeRecipe:
    lr = parse_language(lang) if not isinstance(lang, LanguageRuntime) else lang
    if lr is None:
        lr = LanguageRuntime.PYTHON
    return _RECIPES.get(lr) or _RECIPES[LanguageRuntime.PYTHON]


def label_ar(lang: LanguageRuntime | str | None) -> str:
    lr = parse_language(lang) if not isinstance(lang, LanguageRuntime) else lang
    if lr is None:
        return "بايثون"
    return _LABEL_AR.get(lr, lr.value)


def resolve_language(
    text: str = "",
    *,
    explicit: Any = None,
    default: LanguageRuntime = LanguageRuntime.PYTHON,
) -> tuple[LanguageRuntime, float, str]:
    """Return (language, confidence 0..1, note).

    Priority: explicit package/slot → text detection → default (python).
    """
    exp = parse_language(explicit)
    if exp is not None:
        return exp, 1.0, f"explicit:{exp.value}"

    t = (text or "").strip()
    if not t:
        return default, 0.5, "default_empty_text"

    best: LanguageRuntime | None = None
    best_c = 0.0
    for lang, pat, conf in _DETECT:
        if pat.search(t) and conf > best_c:
            best, best_c = lang, conf

    if best is not None:
        return best, best_c, f"detected:{best.value}"

    return default, 0.55, "default_python"


def language_metadata(
    lang: LanguageRuntime,
    *,
    confidence: float = 1.0,
    note: str = "",
    kind: str = "",
) -> dict[str, Any]:
    rec = recipe_for(lang)
    enabled = is_language_enabled(lang)
    kind_ok = kind_supported_for_language(kind, lang) if kind else True
    return {
        "language": lang.value,
        "language_label_ar": label_ar(lang),
        "language_confidence": round(float(confidence), 3),
        "language_note": note,
        "language_enabled": enabled,
        "language_kind_supported": kind_ok,
        "docker_image": rec.docker_image,
        "package_manager": rec.package_manager,
        "install_command": rec.install_command,
        "default_start_command": rec.default_start,
        "language_manifest_files": list(rec.manifest_files),
        "language_source_globs": list(rec.source_globs),
    }


def assert_language_allowed(
    lang: LanguageRuntime,
    *,
    kind: str = "",
) -> tuple[bool, str]:
    """Gate for IR validate. Phase 1: only enabled languages + matrix."""
    if not is_language_enabled(lang):
        enabled = ",".join(sorted(x.value for x in enabled_languages()))
        return False, (
            f"language_not_enabled:{lang.value}"
            f" (enabled={enabled}; set LUMEN_ENABLED_LANGUAGES to expand)"
        )
    if kind and not kind_supported_for_language(kind, lang):
        return False, f"language_kind_unsupported:{lang.value}+{kind}"
    return True, ""


__all__ = [
    "LanguageRuntime",
    "RuntimeRecipe",
    "parse_language",
    "enabled_languages",
    "is_language_enabled",
    "kind_supported_for_language",
    "recipe_for",
    "label_ar",
    "resolve_language",
    "language_metadata",
    "assert_language_allowed",
]
