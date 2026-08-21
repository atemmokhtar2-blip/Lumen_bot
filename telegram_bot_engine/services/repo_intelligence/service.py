"""
Repo Intelligence — deterministic layer above structural RepoContract.

Computes:
  - dependency gaps (imports vs requirements)
  - env gaps
  - host readiness score
  - capabilities / risks / next actions / change surface
No LLM.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Iterable

from ...schemas.repo_contract import (
    DependencyGap,
    RepoCapability,
    RepoContract,
    RepoIntelligence,
    RepoRisk,
)

_SKIP_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".tbe_venv",
    ".tbe_deps", "site-packages", "dist", "build", ".tox", ".mypy_cache",
    "tests", "test", "docs", "examples", "example", ".github",
}

_STDLIB = {
    "os", "sys", "re", "json", "time", "datetime", "pathlib", "typing",
    "collections", "functools", "itertools", "subprocess", "threading",
    "asyncio", "logging", "http", "urllib", "email", "html", "xml",
    "sqlite3", "hashlib", "hmac", "base64", "uuid", "copy", "math",
    "random", "string", "io", "tempfile", "shutil", "glob", "fnmatch",
    "argparse", "configparser", "csv", "dataclasses", "enum", "abc",
    "contextlib", "traceback", "warnings", "inspect", "importlib",
    "platform", "socket", "ssl", "multiprocessing", "concurrent", "queue",
    "signal", "struct", "zlib", "gzip", "zipfile", "tarfile", "pickle",
    "secrets", "statistics", "decimal", "operator", "pprint", "textwrap",
    "ast", "tokenize", "token", "keyword", "dis", "gc", "sysconfig",
    "heapq", "bisect", "array", "weakref", "types", "copyreg", "pprint",
    "py_compile", "compileall", "runpy", "pkgutil", "modulefinder",
    "unittest", "doctest", "pdb", "profile", "timeit", "trace",
    "difflib", "filecmp", "linecache", "codecs", "unicodedata", "locale",
    "gettext", "calendar", "zoneinfo", "numbers", "fractions", "cmath",
    "select", "selectors", "asyncore", "asynchat", "mmap", "ctypes",
    "threading", "dummy_threading", "sched", "binascii", "quopri",
    "json", "plistlib", "sqlite3", "dbm", "shelve", "csv", "netrc",
    "posixpath", "ntpath", "genericpath", "stat", "fileinput",
}
# test-only packages — gaps ignored for host readiness noise
_TEST_ONLY_PACKAGES = {
    "pytest", "pytest_asyncio", "pytest_cov", "hypothesis", "mock",
    "coverage", "tox", "nox", "mypy", "ruff", "flake8", "black",
    "isort", "pylint", "pyflakes", "bandit",
}


def _module_to_package(module: str) -> str | None:
    try:
        from ..live_runner.service import _module_to_package as m2p
        return m2p(module)
    except Exception:
        top = (module or "").split(".")[0]
        if not top or top in _STDLIB:
            return None
        return top


def _iter_py(root: Path, limit: int = 100) -> Iterable[Path]:
    n = 0
    for p in root.rglob("*.py"):
        if any(x in p.parts for x in _SKIP_DIRS):
            continue
        yield p
        n += 1
        if n >= limit:
            break


def _local_names(root: Path) -> set[str]:
    names: set[str] = set()
    for p in root.rglob("*"):
        if any(x in p.parts for x in _SKIP_DIRS):
            continue
        if p.is_file() and p.suffix == ".py":
            names.add(p.stem)
            if p.name == "__init__.py" and p.parent != root:
                names.add(p.parent.name)
        elif p.is_dir() and (p / "__init__.py").exists():
            names.add(p.name)
    return names


def _ast_third_party_imports(root: Path) -> list[str]:
    local = _local_names(root)
    found: list[str] = []
    for p in _iter_py(root):
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"), filename=str(p))
        except Exception:
            continue
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names if a.name]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for mod in mods:
                top = mod.split(".")[0]
                if not top or top in _STDLIB or top in local:
                    continue
                if mod not in found:
                    found.append(mod)
    return found


def _norm_pkg(name: str) -> str:
    return re.sub(r"[-_]", "", (name or "").lower())


def _req_packages(contract: RepoContract, root: Path) -> set[str]:
    present: set[str] = set()
    for d in contract.dependencies or []:
        pkg = re.split(r"[<>=!~;\[]", d)[0].strip().lower()
        if pkg:
            present.add(_norm_pkg(pkg))
            present.add(_norm_pkg(pkg.replace("-", "_")))
    for name in ("requirements.txt", "requirements-bot.txt", "reqs.txt", "pyproject.toml"):
        p = root / name
        if not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("["):
                continue
            pkg = re.split(r"[<>=!~;\[]", line)[0].strip().lower()
            if pkg and re.match(r"^[a-zA-Z]", pkg):
                present.add(_norm_pkg(pkg))
    return present


def _env_example_names(root: Path) -> set[str]:
    names: set[str] = set()
    for name in (".env.example", ".env.sample", ".env.template"):
        p = root / name
        if not p.exists():
            continue
        try:
            for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                names.add(line.split("=", 1)[0].strip())
        except Exception:
            pass
    return names


def build_repo_intelligence(contract: RepoContract) -> RepoIntelligence:
    root = Path(contract.root_path)
    if not root.is_dir():
        return RepoIntelligence(
            host_readiness=0.0,
            host_ready=False,
            risks=[RepoRisk(code="path_missing", severity="critical", message_ar="مسار المستودع غير موجود")],
            next_actions=["تحقق من مسار السحب"],
        )

    # --- dependency gaps ---
    imports = _ast_third_party_imports(root)
    present = _req_packages(contract, root)
    gaps: list[DependencyGap] = []
    seen_pkg: set[str] = set()
    for mod in imports:
        pkg = _module_to_package(mod)
        if not pkg:
            continue
        if _norm_pkg(pkg) in present or _norm_pkg(pkg.replace("-", "_")) in present:
            continue
        key = _norm_pkg(pkg)
        if key in seen_pkg:
            continue
        if pkg.lower().replace("-", "_") in _TEST_ONLY_PACKAGES or pkg.lower() in _TEST_ONLY_PACKAGES:
            continue
        if mod.split(".")[0].lower() in _TEST_ONLY_PACKAGES:
            continue
        seen_pkg.add(key)
        gaps.append(DependencyGap(module=mod, suggested_package=pkg, evidence="import_not_in_requirements"))

    # --- env gaps ---
    env_declared = {v.name for v in (contract.env_vars or []) if v.name}
    env_example = _env_example_names(root)
    # critical token-like vars referenced in code but not documented in example
    critical_env = {
        n for n in env_declared
        if any(k in n.upper() for k in ("TOKEN", "API_KEY", "SECRET", "PASSWORD", "GEMINI", "OPENAI"))
    }
    env_gaps = sorted(critical_env - env_example)[:15]

    # --- capabilities ---
    capabilities: list[RepoCapability] = []
    for c in (contract.commands or [])[:30]:
        capabilities.append(RepoCapability(name=f"/{c.name}", kind="command", evidence=c.source_file or ""))
    for fw in (contract.frameworks or [])[:8]:
        capabilities.append(RepoCapability(name=fw, kind="integration", evidence="framework"))
    if contract.is_telegram_bot:
        capabilities.append(RepoCapability(name="telegram_bot", kind="feature", evidence="architecture"))
    if any("payment" in (c.name or "").lower() or "pay" in (c.name or "").lower() for c in (contract.commands or [])):
        capabilities.append(RepoCapability(name="payments_hint", kind="feature", evidence="command_name"))
    if any(x in (contract.dependencies or []) or x in str(contract.frameworks) for x in ("openai", "google-generativeai", "anthropic")):
        capabilities.append(RepoCapability(name="ai_integration", kind="integration", evidence="dependency"))
    # from imports
    for mod in imports:
        if "generativeai" in mod or mod.startswith("openai"):
            capabilities.append(RepoCapability(name="ai_integration", kind="integration", evidence=mod))
            break

    # dedupe capabilities by name
    cap_seen: set[str] = set()
    caps_u: list[RepoCapability] = []
    for c in capabilities:
        if c.name not in cap_seen:
            cap_seen.add(c.name)
            caps_u.append(c)

    # --- risks ---
    risks: list[RepoRisk] = []
    if contract.is_telegram_bot and not contract.entry_points:
        risks.append(RepoRisk(code="no_entry", severity="high", message_ar="بوت بدون نقطة دخول واضحة"))
    if contract.is_telegram_bot and not contract.commands:
        risks.append(RepoRisk(code="no_commands", severity="medium", message_ar="لم تُستخرج أوامر مسجّلة"))
    if gaps:
        risks.append(RepoRisk(
            code="dep_gaps",
            severity="high",
            message_ar=f"{len(gaps)} تبعية مستوردة غير مذكورة في requirements",
        ))
    if contract.architecture_style == "library" and contract.is_telegram_bot:
        risks.append(RepoRisk(code="lib_vs_bot", severity="medium", message_ar="تصنيف متردد بين مكتبة وبوت"))
    qs = contract.quality_signals or {}
    if contract.is_telegram_bot and not qs.get("has_tests"):
        risks.append(RepoRisk(code="no_tests", severity="low", message_ar="لا اختبارات ظاهرة"))
    if not contract.is_telegram_bot and not contract.is_generation_engine:
        risks.append(RepoRisk(code="not_bot", severity="medium", message_ar="المشروع قد لا يكون بوت تليجرام قابلاً للاستضافة مباشرة"))

    # --- change surface ---
    surface: list[str] = []
    for ep in (contract.entry_points or [])[:3]:
        if ep.path:
            surface.append(ep.path)
    for c in (contract.commands or [])[:5]:
        if c.source_file and c.source_file not in surface:
            surface.append(c.source_file)
    for name in ("handlers.py", "bot.py", "main.py", "keyboards.py"):
        if (root / name).exists() and name not in surface:
            surface.append(name)

    # --- host readiness ---
    score = 0.0
    if contract.is_telegram_bot:
        score += 0.35
    if contract.entry_points:
        score += 0.2
    if contract.commands:
        score += 0.1
    if contract.frameworks:
        score += 0.1
    if not gaps:
        score += 0.15
    else:
        score += max(0.0, 0.15 - 0.03 * len(gaps))
    if contract.confidence >= 0.6:
        score += 0.05
    if qs.get("has_async"):
        score += 0.03
    if qs.get("has_tests"):
        score += 0.02
    if any(r.severity in ("critical", "high") and r.code == "no_entry" for r in risks):
        score -= 0.2
    score = round(min(0.99, max(0.0, score)), 3)
    host_ready = bool(
        contract.is_telegram_bot
        and contract.entry_points
        and score >= 0.55
        and not any(r.code == "no_entry" for r in risks)
    )

    # --- next actions ---
    actions: list[str] = []
    if gaps:
        pkgs = ", ".join(g.suggested_package for g in gaps[:5] if g.suggested_package)
        actions.append(f"أضف التبعيات الناقصة: {pkgs}")
    if env_gaps:
        actions.append("وثّق متغيرات البيئة الحساسة في .env.example")
    if host_ready:
        actions.append("جاهز للاستضافة: اكتب «استضف» بعد التأكد من التوكن")
    elif contract.is_telegram_bot and gaps:
        actions.append("أصلح فجوات التبعيات ثم أعد الفهم/الاستضافة")
    elif contract.is_telegram_bot and not contract.entry_points:
        actions.append("حدد نقطة دخول (main.py/bot.py) قبل الاستضافة")
    if contract.is_telegram_bot and contract.commands:
        actions.append("يمكن التطوير التكراري: أضف/احذف أمر على المستودع النشط")
    if not actions:
        actions.append("راجع الملخص الهيكلي وحدّد هدف التطوير")

    notes: list[str] = []
    # Package Reality (live PyPI) — best-effort, never breaks understand
    package_health_score = None
    package_alerts: list[str] = []
    try:
        from ..package_reality import assess_repo_packages
        preport = assess_repo_packages(root)
        package_health_score = preport.health_score
        for p in preport.packages:
            if p.status in ("yanked", "major_lag", "not_on_pypi", "outdated"):
                package_alerts.append(f"{p.name}:{p.status}")
        package_alerts = package_alerts[:12]
        if preport.major_lag_count or preport.yanked_count:
            risks.append(RepoRisk(
                code="package_health",
                severity="high" if preport.yanked_count or preport.major_lag_count else "medium",
                message_ar=(
                    f"صحة الحزم: outdated={preport.outdated_count} "
                    f"major_lag={preport.major_lag_count} yanked={preport.yanked_count}"
                ),
            ))
            score = max(0.0, score - 0.05 * preport.major_lag_count - 0.08 * preport.yanked_count)
            score = round(min(0.99, score), 3)
            host_ready = bool(
                contract.is_telegram_bot
                and contract.entry_points
                and score >= 0.55
                and not any(r.code == "no_entry" for r in risks)
            )
    except Exception as e:
        notes.append(f"package_reality_skip:{type(e).__name__}")

    return RepoIntelligence(
        host_readiness=score,
        host_ready=host_ready,
        dependency_gaps=gaps[:20],
        env_gaps=env_gaps,
        capabilities=caps_u[:25],
        risks=risks[:15],
        next_actions=actions[:8],
        change_surface=surface[:10],
        package_health_score=package_health_score,
        package_alerts=package_alerts,
        notes=notes + ["repo_intelligence_v1"],
    )


def enrich_repo_contract(contract: RepoContract) -> RepoContract:
    """Attach intelligence layer onto an existing contract (safe copy)."""
    if contract is None:
        return RepoContract(ok=False, message="no_contract", confidence=0.0)
    try:
        intel = build_repo_intelligence(contract)
    except Exception:
        return contract
    try:
        return contract.model_copy(update={"intelligence": intel, "schema_version": "2.1"})
    except Exception:
        try:
            contract.intelligence = intel
            contract.schema_version = "2.1"
        except Exception:
            pass
        return contract
