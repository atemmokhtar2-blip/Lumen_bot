"""
FidelityGate — contract ↔ generated project coverage.

Rejects projects that:
  - miss handlers for contract commands
  - miss model classes for contract entities
  - miss service modules for contract services
  - dump raw long summary into /start (NL leak)
  - lack structural layers when modular_code / clean layers requested

Does NOT inject domain knowledge. Operates only on ProgramContract + files.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FidelityFinding:
    severity: str  # error | warning
    code: str
    message: str
    evidence: str = ""


@dataclass
class FidelityReport:
    ok: bool
    findings: list[FidelityFinding] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)

    @property
    def errors(self) -> list[FidelityFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[FidelityFinding]:
        return [f for f in self.findings if f.severity == "warning"]


def _load_contract(root: Path) -> dict[str, Any] | None:
    path = root / "program_contract.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _main_src(root: Path) -> str:
    p = root / "app" / "main.py"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _start_src(root: Path) -> str:
    p = root / "app" / "handlers" / "start.py"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _models_src(root: Path) -> str:
    p = root / "app" / "models.py"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def check_project_fidelity(project_dir: str | Path) -> FidelityReport:
    root = Path(project_dir)
    findings: list[FidelityFinding] = []
    coverage: dict[str, Any] = {
        "commands_total": 0,
        "commands_covered": 0,
        "entities_total": 0,
        "entities_covered": 0,
        "services_total": 0,
        "services_covered": 0,
    }

    if not root.exists():
        return FidelityReport(
            ok=False,
            findings=[FidelityFinding("error", "no_project", "مجلد المشروع غير موجود")],
        )

    contract = _load_contract(root)
    if contract is None:
        findings.append(
            FidelityFinding(
                "error",
                "no_contract",
                "program_contract.json مفقود — لا يمكن التحقق من الإخلاص",
            )
        )
        return FidelityReport(ok=False, findings=findings, coverage=coverage)

    main = _main_src(root)
    start = _start_src(root)
    models = _models_src(root)
    handlers_dir = root / "app" / "handlers"
    services_dir = root / "app" / "services"

    # --- commands coverage ---
    commands = list(contract.get("commands") or [])
    coverage["commands_total"] = len(commands)
    for cmd in commands:
        name = (cmd.get("name") or "").strip().lower()
        if not name:
            continue
        covered = False
        def _registered(cmd: str) -> bool:
            # PTB
            if f'CommandHandler("{cmd}"' in main or f"CommandHandler('{cmd}'" in main:
                return True
            # aiogram 3
            if f'Command("{cmd}")' in main or f"Command('{cmd}')" in main:
                return True
            return False

        if name in ("start", "help"):
            covered = _registered(name)
            if name == "start" and "start_handler" not in start and "start_handler" not in main:
                covered = False
        else:
            safe = re.sub(r"[^a-z0-9_]", "_", name)
            cmd_file = handlers_dir / f"cmd_{safe}.py"
            covered = cmd_file.exists() and _registered(name)
        if covered:
            coverage["commands_covered"] += 1
        else:
            findings.append(
                FidelityFinding(
                    "error",
                    "missing_command_handler",
                    f"الأمر /{name} في العقد بلا handler في المشروع",
                    evidence=name,
                )
            )

    # --- entities → models ---
    entities = list(contract.get("entities") or [])
    coverage["entities_total"] = len(entities)
    for ent in entities:
        ename = (ent.get("name") or "").strip()
        if not ename:
            continue
        if re.search(rf"class\s+{re.escape(ename)}\b", models):
            coverage["entities_covered"] += 1
        else:
            findings.append(
                FidelityFinding(
                    "error",
                    "missing_entity_model",
                    f"الكيان `{ename}` في العقد بلا class في models.py",
                    evidence=ename,
                )
            )

    # --- services ---
    services = list(contract.get("services") or [])
    coverage["services_total"] = len(services)
    for svc in services:
        sname = (svc.get("name") or "").strip().lower()
        if not sname:
            continue
        safe = re.sub(r"[^a-z0-9_]", "_", sname)
        if (services_dir / f"{safe}.py").exists():
            coverage["services_covered"] += 1
        else:
            findings.append(
                FidelityFinding(
                    "error",
                    "missing_service_module",
                    f"الخدمة `{sname}` في العقد بلا ملف services/{safe}.py",
                    evidence=sname,
                )
            )

    # --- NL leak into /start (long summary dump) ---
    summary = (contract.get("summary") or "").strip()
    if summary and len(summary) > 40 and start:
        leaked = False
        evidence = ""
        for tok in re.findall(r"[A-Za-z0-9_]{16,}", summary):
            if tok in start:
                leaked, evidence = True, tok[:40]
                break
        if not leaked:
            probe = re.sub(r"\s+", " ", summary)[:40].strip()
            if len(probe) >= 20 and probe in start:
                leaked, evidence = True, probe
        if leaked:
            findings.append(
                FidelityFinding(
                    "error",
                    "summary_leak_in_start",
                    "رسالة /start تلصق ملخص المستخدم الخام — ممنوع",
                    evidence=evidence,
                )
            )

    # --- structural layers when rules request clean architecture ---
    rules = list(contract.get("architecture_rules_applied") or [])
    wants_layers = any("CLEAN" in r.upper() or "R11" in r for r in rules)
    quality = contract.get("quality") or {}
    if wants_layers or quality.get("modular_code"):
        for rel in (
            "app/repositories.py",
            "app/container.py",
        ):
            if not (root / rel).exists():
                findings.append(
                    FidelityFinding(
                        "warning",
                        "missing_layer",
                        f"طبقة متوقعة ناقصة: {rel}",
                        evidence=rel,
                    )
                )

    # --- tech postgres signal ---
    tech = contract.get("tech") or {}
    if tech.get("database") == "postgres":
        req = root / "requirements.txt"
        req_txt = req.read_text(encoding="utf-8") if req.exists() else ""
        if "asyncpg" not in req_txt and "psycopg" not in req_txt:
            findings.append(
                FidelityFinding(
                    "error",
                    "postgres_not_in_requirements",
                    "العقد يطلب postgres لكن requirements لا تتضمن asyncpg/psycopg",
                )
            )


    # --- framework from architecture ---
    arch = contract.get("architecture") or {}
    fw = (arch.get("framework") or "").lower()
    req = root / "requirements.txt"
    req_txt = req.read_text(encoding="utf-8") if req.exists() else ""
    if "aiogram" in fw:
        if "aiogram" not in req_txt:
            findings.append(
                FidelityFinding(
                    "error",
                    "framework_mismatch",
                    "العقد يطلب aiogram لكن requirements لا تتضمنه",
                )
            )
        main = _main_src(root)
        if "aiogram" not in main and "Dispatcher" not in main:
            findings.append(
                FidelityFinding(
                    "error",
                    "framework_main_mismatch",
                    "العقد يطلب aiogram لكن main.py ليس على aiogram",
                )
            )
    elif fw and "telegram" in fw:
        if "python-telegram-bot" not in req_txt and "telegram" not in req_txt:
            findings.append(
                FidelityFinding(
                    "warning",
                    "framework_ptb_soft",
                    "توقّع python-telegram-bot في requirements",
                )
            )

    # --- declared layers exist ---
    layers = list(arch.get("layers") or [])
    layer_map = {
        "handlers": "app/handlers",
        "services": "app/services",
        "repositories": "app/repositories.py",
        "middlewares": "app/middlewares.py",
        "filters": "app/filters.py",
        "models": "app/models.py",
        "config": "app/config.py",
        "configurations": "app/config.py",
        "utils": "app/utils.py",
        "utilities": "app/utils.py",
        "domain": "app/domain",
        "usecases": "app/usecases",
    }
    for layer in layers:
        key = "".join(ch for ch in layer.lower() if ch.isalnum() or ch == "_")
        # soft match
        path = None
        for k, v in layer_map.items():
            if k in key or key in k:
                path = v
                break
        if path is None:
            continue
        full = root / path
        if not full.exists():
            findings.append(
                FidelityFinding(
                    "error",
                    "missing_declared_layer",
                    f"طبقة معلنة في العقد ناقصة: {layer} → {path}",
                    evidence=layer,
                )
            )
    if arch.get("dependency_injection") and not (root / "app" / "container.py").exists():
        findings.append(
            FidelityFinding(
                "error",
                "missing_di_container",
                "العقد يطلب Dependency Injection بلا container.py",
            )
        )

    # coverage ratios
    def _ratio(a: int, b: int) -> float:
        return 1.0 if b == 0 else round(a / b, 3)

    coverage["commands_ratio"] = _ratio(coverage["commands_covered"], coverage["commands_total"])
    coverage["entities_ratio"] = _ratio(coverage["entities_covered"], coverage["entities_total"])
    coverage["services_ratio"] = _ratio(coverage["services_covered"], coverage["services_total"])

    ok = not any(f.severity == "error" for f in findings)
    return FidelityReport(ok=ok, findings=findings, coverage=coverage)


def fidelity_as_dict(report: FidelityReport) -> dict[str, Any]:
    return {
        "ok": report.ok,
        "errors": [f.message for f in report.errors],
        "warnings": [f.message for f in report.warnings],
        "findings": [
            {
                "severity": f.severity,
                "code": f.code,
                "message": f.message,
                "evidence": f.evidence,
            }
            for f in report.findings
        ],
        "coverage": report.coverage,
    }
