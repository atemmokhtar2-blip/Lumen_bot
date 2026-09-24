"""Acceptance checks for agent-built projects — kind-aware (Phase 2)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


_ENTRY_CANDIDATES = (
    "main.py",
    "app.py",
    "bot.py",
    "src/main.py",
    "src/bot.py",
    "src/__init__.py",
)

_TG_IMPORT = ("telegram", "aiogram", "pyrogram", "telebot", "python-telegram-bot")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _has_tg_import(root: Path, files: set[str]) -> bool:
    for rel in files:
        if not rel.endswith(".py"):
            continue
        text = _read(root / rel).lower()
        if any(x in text for x in _TG_IMPORT):
            return True
    return False


def _deps_text(root: Path, files: set[str]) -> str:
    for name in ("requirements.txt", "pyproject.toml", "Pipfile"):
        if name in files:
            return _read(root / name).lower()
    return ""


def check_agent_project(
    work_dir: str | Path,
    *,
    goal: str = "",
    project_kind: str = "",
) -> dict[str, Any]:
    """Validate generated tree. When project_kind is set, enforce kind rules."""
    root = Path(work_dir)
    missing: list[str] = []
    found: list[str] = []
    warnings: list[str] = []

    if not root.exists():
        return {"ok": False, "missing": ["work_dir"], "found": [], "warnings": [], "score": 0.0, "project_kind": project_kind}

    files = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    files = {f for f in files if not f.endswith("CLINE_AGENT.md") and ".git/" not in f}

    kind = (project_kind or "").strip().lower()
    if not kind and goal:
        try:
            from lumen.engine.core.project_kind import resolve_project_kind
            kind = resolve_project_kind(text=goal).value
        except Exception:
            kind = ""

    entry = None
    for cand in _ENTRY_CANDIDATES:
        if cand in files:
            entry = cand
            found.append(cand)
            break
    if not entry and kind != "library":
        missing.append("entry_point (main.py|app.py|bot.py)")

    has_req = any(n in files for n in ("requirements.txt", "pyproject.toml", "Pipfile"))
    if has_req:
        found.append("deps_manifest")
    else:
        missing.append("requirements.txt|pyproject.toml")

    has_readme = any(name.lower().startswith("readme") for name in files)
    if has_readme:
        found.append("readme")
    else:
        warnings.append("no_readme")

    py_files = [f for f in files if f.endswith(".py")]
    if not py_files:
        missing.append("any_python_file")
    else:
        found.append(f"py_count:{len(py_files)}")

    if entry:
        try:
            import py_compile
            py_compile.compile(str(root / entry), doraise=True)
            found.append("entry_compiles")
        except Exception as exc:
            missing.append(f"entry_syntax:{type(exc).__name__}")

    deps = _deps_text(root, files)
    tg_imports = _has_tg_import(root, files)
    entry_text = _read(root / entry).lower() if entry else ""

    # --- kind-specific gates ---
    if kind == "telegram_bot":
        if tg_imports or "telegram" in deps:
            found.append("telegram_lib")
        elif goal and ("بوت" in goal or "bot" in goal.lower() or "telegram" in goal.lower()):
            warnings.append("no_telegram_import_detected")
        if entry and ("getenv" in entry_text or "environ" in entry_text):
            found.append("token_from_env_likely")

    elif kind in {"web_site", "web_api"}:
        if tg_imports:
            missing.append("forbidden_telegram_import")
        if "fastapi" in deps or "flask" in deps or "fastapi" in entry_text or "flask" in entry_text:
            found.append("web_framework")
        else:
            missing.append("fastapi_or_flask_required")
        blob = entry_text + " ".join(_read(root / f).lower() for f in files if f.endswith(".py"))[:8000]
        # Hard gate: health route must exist for web kinds
        if "/health" in blob or '@app.get("/health")' in blob or "@app.get('/health')" in blob:
            found.append("health_route")
        elif "health" in blob and ("route" in blob or "get(" in blob or "get (" in blob):
            found.append("health_route_signal")
        else:
            missing.append("GET_/health_required")
        if kind == "web_site":
            has_root = (
                '@app.get("/")' in blob
                or "@app.get('/') " in blob
                or '@app.get("/")' in entry_text
                or 'route("/")' in blob
                or "route('/')" in blob
            )
            if has_root or "TemplateResponse" in blob or "htmlresponse" in blob:
                found.append("root_route")
            else:
                # soft: seed always provides it; still flag
                warnings.append("no_root_route_signal")
            has_html = any(f.endswith(".html") for f in files) or "templates/" in " ".join(files)
            has_static = any(f.startswith("static/") for f in files)
            if has_html or has_static:
                found.append("site_assets")
            else:
                warnings.append("no_html_or_static")

    elif kind == "cli_app":
        if tg_imports:
            missing.append("forbidden_telegram_import")
        if "argparse" in entry_text or "click" in entry_text or "typer" in entry_text:
            found.append("cli_parser")
        else:
            warnings.append("no_argparse_click_typer")

    elif kind == "library":
        if tg_imports:
            missing.append("forbidden_telegram_import")
        if "src/" in " ".join(files) or "pyproject.toml" in files:
            found.append("package_layout")
        else:
            warnings.append("no_package_layout")

    elif kind and kind not in {"telegram_bot", "discord_bot", "whatsapp_bot", "refine"}:
        if tg_imports:
            warnings.append("unexpected_telegram_import")

    # Execution-based verification when FastAPI is available (stronger than static scan)
    if kind in {"web_site", "web_api"} and entry and "forbidden_telegram_import" not in missing:
        try:
            import importlib.util
            import sys as _sys
            _root_s = str(root.resolve())
            if _root_s not in _sys.path:
                _sys.path.insert(0, _root_s)
            spec = importlib.util.spec_from_file_location("_lumen_entry", str(root / entry))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                app = getattr(mod, "app", None)
                if app is not None:
                    from fastapi.testclient import TestClient
                    client = TestClient(app)
                    hr = client.get("/health")
                    if hr.status_code == 200:
                        found.append("asgi_health_probe")
                    else:
                        missing.append(f"health_http_{hr.status_code}")
                    if kind == "web_site":
                        home = client.get("/")
                        if home.status_code == 200:
                            found.append("asgi_root_probe")
                        else:
                            warnings.append(f"root_http_{home.status_code}")
                else:
                    warnings.append("no_app_export_for_uvicorn")
        except ImportError:
            warnings.append("fastapi_not_installed_for_probe")
        except Exception as _probe_exc:
            warnings.append(f"asgi_probe_error:{type(_probe_exc).__name__}")


    # Phase 5: no raw system / shell abuse in delivered tree
    try:
        from lumen.engine.security.phase5_bounds import scan_project_for_dangerous_code
        danger = scan_project_for_dangerous_code(root)
        if danger:
            missing.append("dangerous_system_code:" + ",".join(danger[:4]))
    except Exception:
        pass

    # Phase 5: python-only tree
    try:
        pys = [p for p in root.rglob("*.py") if p.is_file() and "__pycache__" not in p.parts]
        if kind in {"web_site", "web_api", "telegram_bot", "cli_app", "general_app"} and not pys:
            missing.append("python_source_required")
        for name in ("package.json", "Cargo.toml", "go.mod", "pom.xml", "composer.json"):
            if (root / name).is_file():
                missing.append(f"non_python_manifest:{name}")
    except Exception:
        pass

    must = 3
    got = sum([bool(entry or kind == "library"), has_req, bool(py_files)])
    score = got / must
    critical = {
        m for m in missing
        if m.startswith("entry_point")
        or m.startswith("requirements")
        or m.startswith("any_python")
        or m.startswith("entry_syntax")
        or m == "work_dir"
        or m == "forbidden_telegram_import"
        or m == "GET_/health_required"
        or m == "fastapi_or_flask_required"
        or m.startswith("health_http_")
        or m.startswith("dangerous_system_code")
        or m.startswith("non_python_manifest")
        or m == "python_source_required"
    }
    ok = got >= 2 and (bool(entry) or kind == "library") and not critical


    return {
        "ok": ok,
        "score": round(score, 2),
        "missing": missing,
        "found": found,
        "warnings": warnings,
        "entry": entry,
        "file_count": len(files),
        "project_kind": kind,
    }


__all__ = ["check_agent_project"]
