"""
HostingService — foundation for paid hosting (no billing yet).

Manages long-running bot processes for the owner:
  start / stop / status / diagnose (via Error Intelligence)

Uses LocalProcessDriver for real process lifecycle and Error Intelligence
for log diagnosis. State persisted under OUTPUT_DIR/hosting_state.json.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ...schemas.error_contract import ErrorContract
from .state_lock import atomic_write_text, exclusive_state_lock
from .state_store import HostingStateStore, get_host_state_store


@dataclass
class HostInstance:
    instance_id: str
    user_id: int
    project_path: str
    entry_point: str = ""
    bot_username: str = ""
    status: str = "stopped"  # starting | running | stopped | failed
    deployment_id: str = ""
    pid: int | None = None
    started_at: float = 0.0
    last_error: str = ""
    last_diagnosis: dict[str, Any] = field(default_factory=dict)
    token_fp: str = ""  # sha256[:16] of bot token — never store raw token


@dataclass
class HostResult:
    ok: bool
    message: str
    instance: HostInstance | None = None
    error_contract: ErrorContract | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_user_text(self) -> str:
        icon = "✅" if self.ok else "❌"
        lines = [f"{icon} *استضافة*", f"• {self.message}"]
        if self.instance:
            inst = self.instance
            lines.append(f"• الحالة: `{inst.status}`")
            if inst.bot_username:
                lines.append(f"• البوت: @{inst.bot_username}")
            if inst.instance_id:
                lines.append(f"• المعرّف: `{inst.instance_id}`")
            if inst.pid:
                lines.append(f"• PID: `{inst.pid}`")
            if inst.project_path:
                lines.append(f"• المسار: `{inst.project_path}`")
            if inst.last_error:
                lines.append(f"• آخر خطأ: {inst.last_error[:200]}")
        if self.error_contract and self.error_contract.primary:
            lines.append("• تشخيص:")
            lines.append(self.error_contract.to_user_summary())
        return "\n".join(lines)


class HostingService:
    """Owner-scoped hosting manager."""

    def __init__(self, state_dir: str | Path | None = None) -> None:
        base = Path(state_dir or os.getenv("OUTPUT_DIR", "/tmp/generated")).resolve()
        self.output_root = base
        self.state_dir = base / "hosting"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "instances.json"  # legacy JSON (migrated once)
        self._store = get_host_state_store(self.state_dir / "instances.sqlite3")
        self._instances: dict[str, HostInstance] = {}
        self._load()

    def _lock_path(self) -> Path:
        return self.state_dir / "instances.lock"

    def _inst_from_row(self, row: dict) -> HostInstance:
        return HostInstance(**{
            k: v for k, v in row.items()
            if k in HostInstance.__dataclass_fields__
        })

    def _load_unlocked(self) -> None:
        """Reload registry from SQLite (source of truth); migrate legacy JSON once."""
        try:
            rows = self._store.list_all()
            if not rows and self.state_file.exists():
                # one-time migration from legacy JSON
                try:
                    data = json.loads(self.state_file.read_text(encoding="utf-8"))
                    for row in data.get("instances", []):
                        inst = self._inst_from_row(row)
                        self._store.upsert(asdict(inst))
                    rows = self._store.list_all()
                    # archive legacy file
                    try:
                        self.state_file.rename(self.state_file.with_suffix(".json.migrated"))
                    except Exception:
                        pass
                except Exception:
                    rows = []
            self._instances = {
                r["instance_id"]: self._inst_from_row(r) for r in rows
            }
        except Exception:
            self._instances = {}

    def _load(self) -> None:
        try:
            with exclusive_state_lock(self._lock_path()):
                self._load_unlocked()
        except Exception:
            self._instances = {}

    def _save_unlocked(self) -> None:
        """Persist each instance to SQLite (transactional source of truth)."""
        for inst in self._instances.values():
            self._store.upsert(asdict(inst))

    def _save(self) -> None:
        with exclusive_state_lock(self._lock_path()):
            self._save_unlocked()

    def list_for_user(self, user_id: int) -> list[HostInstance]:
        return [i for i in self._instances.values() if i.user_id == user_id]

    def get(self, instance_id: str, user_id: int | None = None) -> HostInstance | None:
        inst = self._instances.get(instance_id)
        if inst is None:
            return None
        if user_id is not None and inst.user_id != user_id:
            return None
        return inst

    def start(
        self,
        *,
        user_id: int,
        project_path: str | Path,
        bot_token: str,
        bot_username: str = "",
    ) -> HostResult:
        path = Path(project_path).resolve()
        if not path.is_dir():
            return HostResult(ok=False, message="مسار المشروع غير موجود")

        # Containment: must live under THIS user's sandbox (IDOR root fix).
        # API layer already checks tenant sandbox; HostService enforces the same
        # invariant so internal callers cannot host another tenant's tree.
        try:
            from telegram_bot_engine.services.user_sandbox import get_user_sandbox
            sandbox = get_user_sandbox(int(user_id), self.output_root)
            if not sandbox.is_under_sandbox(path):
                return HostResult(ok=False, message="مسار المشروع خارج مساحة عزل المستخدم")
            try:
                from telegram_bot_engine.services.disk_quota import enforce_user_quota
                enforce_user_quota(sandbox.root)
            except RuntimeError as exc:
                return HostResult(ok=False, message=f"حصة التخزين ممتلئة: {exc}")
        except Exception:
            return HostResult(ok=False, message="مسار المشروع خارج مساحة العزل")


        # ── Production / scale foundation gates ──────────────────────────
        try:
            from telegram_bot_engine.services.isolation_policy import (
                decide_isolation,
                is_dev_environment,
            )
            decision = decide_isolation()
            if decision.require_docker:
                from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
                    docker_available,
                )
                if not docker_available():
                    return HostResult(
                        ok=False,
                        message=(
                            "الاستضافة تتطلب Docker على هذه العقدة. "
                            "LocalProcess غير مسموح في وضع الإنتاج/متعدد المستأجرين."
                        ),
                    )
            if not is_dev_environment():
                db = (os.environ.get("TBE_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
                require_db = (os.environ.get("TBE_REQUIRE_DATABASE_URL") or "1").strip().lower() in {
                    "1", "true", "yes", "on",
                }
                if require_db and not db:
                    return HostResult(
                        ok=False,
                        message=(
                            "في الإنتاج يجب ضبط TBE_DATABASE_URL (PostgreSQL) "
                            "لحالة الاستضافة القابلة للتوسع. "
                            "أو اضبط TBE_REQUIRE_DATABASE_URL=0 للتطوير فقط."
                        ),
                    )
                if decision.require_docker and not (os.environ.get("TBE_DOCKER_NETWORK") or "").strip():
                    return HostResult(
                        ok=False,
                        message="TBE_DOCKER_NETWORK مطلوب في الإنتاج (شبكة محدودة الخروج).",
                    )
        except Exception as gate_exc:
            return HostResult(ok=False, message=f"فشل بوابة الاستضافة: {gate_exc}")


        # Commercial market gate — refuse to sell weak hosting
        try:
            from telegram_bot_engine.services.hosting.market_gate import evaluate_market_gate
            gate = evaluate_market_gate()
            if not gate.ok:
                return HostResult(ok=False, message=gate.message_ar())
        except Exception as gate_exc:
            return HostResult(ok=False, message=f"فشل بوابة السوق: {gate_exc}")

        import hashlib
        token_norm = (bot_token or "").strip()

        token_fp = hashlib.sha256(token_norm.encode()).hexdigest()[:16] if token_norm else ""

        # ── Scale mode (20k path): enqueue for workers, never block API on docker build ──
        scale = (os.environ.get("TBE_SCALE_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}
        multi = (os.environ.get("TBE_MULTI_TENANT") or "1").strip().lower() in {"1", "true", "yes", "on"}
        if scale or (os.environ.get("TBE_FORCE_QUEUE") or "0").strip().lower() in {"1", "true", "yes", "on"}:
            try:
                from telegram_bot_engine.services.hosting.deploy_queue import get_deploy_queue
                from telegram_bot_engine.services.hosting.capacity import estimate_nodes_for, local_node_capacity
                q = get_deploy_queue()
                max_bots = int((os.environ.get("TBE_MAX_BOTS_PER_USER") or "50").strip() or "50")
                running_u = 0
                if hasattr(q, "count_running_for_user"):
                    running_u = int(q.count_running_for_user(int(user_id)))
                else:
                    running_u = sum(1 for i in self.list_for_user(int(user_id)) if i.status == "running")
                if running_u >= max_bots:
                    return HostResult(ok=False, message=f"وصلت للحد الأقصى ({max_bots}) بوت مستضاف لحسابك.")
                # Portable artifact so ANY worker node can build (not only this host's disk)
                from telegram_bot_engine.services.hosting.artifacts import package_project, publish_artifact
                import uuid as _uuid
                pre_id = f"job_{_uuid.uuid4().hex}"
                zip_path, digest = package_project(path, pre_id)
                artifact_uri = publish_artifact(zip_path, pre_id)
                job = q.enqueue(
                    user_id=int(user_id),
                    project_path=str(path),
                    bot_token=token_norm,
                    meta={
                        "bot_username": bot_username or "",
                        "artifact_uri": artifact_uri,
                        "artifact_sha256": digest,
                        "artifact_job_key": pre_id,
                    },
                )
                plan = estimate_nodes_for(20_000)
                return HostResult(
                    ok=True,
                    message=(
                        f"تمت إضافة مهمة الاستضافة للطابور.\n"
                        f"job_id: `{job.job_id}`\n"
                        f"الحالة: queued — العمال (workers) سيلتقطونها.\n"
                        f"لتشغيل عامل على هذه العقدة:\n"
                        f"`python -m telegram_bot_engine.services.hosting.worker`\n"
                        f"تخطيط 20k: ~{plan['nodes_required']} عقدة × {plan['bots_per_node']} بوت "
                        f"(حد العقدة {local_node_capacity().max_bots})."
                    ),
                    instance_id=job.job_id,
                )
            except Exception as qexc:
                return HostResult(ok=False, message=f"فشل إدخال الطابور: {type(qexc).__name__}: {qexc}")

        # Stop existing instance for same path+user OR same token under exclusive lock
        # (closes TOCTOU race between concurrent start requests).
        to_stop: list[str] = []
        with exclusive_state_lock(self._lock_path()):
            self._load_unlocked()
            for inst in list(self._instances.values()):
                if inst.user_id != user_id:
                    continue
                same_path = Path(inst.project_path).resolve() == path and inst.status == "running"
                same_token = (
                    inst.status == "running"
                    and token_fp
                    and (getattr(inst, "token_fp", "") or "") == token_fp
                )
                if same_path or same_token:
                    to_stop.append(inst.instance_id)
        for iid in to_stop:
            self.stop(instance_id=iid, user_id=user_id)

        # Clear webhook so the hosted bot can poll exclusively
        try:
            from bot_interface.singleton import clear_telegram_webhook

            clear_telegram_webhook(token_norm)
        except Exception:
            pass

        # Never host with the platform's own token (would kill the SaaS bot)
        platform_tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        if platform_tok and token_norm and token_norm == platform_tok:
            return HostResult(
                ok=False,
                message=(
                    "لا يمكن استضافة بوت بنفس توكن المنصة. "
                    "أنشئ بوت جديد من @BotFather واستخدم التوكن الخاص به."
                ),
            )

        # Isolation: central fail-closed policy (Docker required in multi-tenant)
        try:
            from telegram_bot_engine.engines.generators.live_deployment.token_validator import (
                TokenValidator,
            )
            from telegram_bot_engine.services.isolation_policy import select_process_driver
        except Exception as e:
            return HostResult(ok=False, message=f"تعذر تحميل محرك الاستضافة: {e}")

        tv = TokenValidator().validate(bot_token)
        if not getattr(tv, "valid", False):
            msg = getattr(tv, "error", None) or "توكن غير صالح"
            return HostResult(ok=False, message=f"التوكن غير صالح: {msg}")

        username = bot_username or getattr(tv, "bot_username", "") or ""
        try:
            driver, _decision = select_process_driver()
        except RuntimeError as exc:
            return HostResult(
                ok=False,
                message=f"عزل الاستضافة مرفوض: {exc}",
            )

        # Token surface: prefer sealed token file; avoid scattering raw token keys
        env = {
            "TELEGRAM_BOT_TOKEN": bot_token,
            "BOT_TOKEN": bot_token,
        }
        status = driver.deploy(
            str(path),
            env_vars=env,
            service_name=f"host-u{user_id}",
        )

        dep_id = getattr(status, "deployment_id", "") or ""
        st = getattr(status, "status", "") or ""
        message = getattr(status, "message", "") or ""
        # pid may only appear inside the message from LocalProcessDriver
        import re as _re
        import uuid
        pid = None
        m_pid = _re.search(r"pid=(\d+)", message)
        if m_pid:
            pid = int(m_pid.group(1))

        instance_id = f"host-{uuid.uuid4().hex[:10]}"
        running_like = st in ("running", "deploy_running") or "running" in st.lower()
        failed_like = "fail" in st.lower()
        inst = HostInstance(
            instance_id=instance_id,
            user_id=user_id,
            project_path=str(path),
            entry_point="",
            bot_username=username,
            status="running" if running_like else ("failed" if failed_like else (st or "unknown")),
            deployment_id=str(dep_id),
            pid=pid,
            started_at=time.time(),
            last_error="" if not failed_like else message,
            token_fp=token_fp,
        )

        # Normalize status using known constants
        try:
            from telegram_bot_engine.engines.generators.live_deployment.report_data import (
                DEPLOY_RUNNING,
                DEPLOY_FAILED,
            )
            if st == DEPLOY_RUNNING:
                inst.status = "running"
            elif st == DEPLOY_FAILED:
                inst.status = "failed"
        except Exception:
            pass

        if inst.status == "failed":
            # Diagnose logs if available
            run_log = getattr(status, "run_log", "") or ""
            install_log = getattr(status, "install_log", "") or message
            contract = None
            try:
                from ..error_intelligence import analyze_logs
                contract = analyze_logs(
                    run_log=run_log,
                    install_log=install_log,
                    phase="run",
                    extra_errors=[message] if message else None,
                )
                if contract.primary:
                    inst.last_diagnosis = {
                        "category": contract.primary.category,
                        "action": contract.primary.suggested_action,
                        "summary_ar": contract.primary.summary_ar,
                        "package": contract.primary.suggested_package,
                    }
                    inst.last_error = contract.primary.summary_ar or message
            except Exception:
                contract = None
            self._instances[instance_id] = inst
            self._save()
            return HostResult(
                ok=False,
                message=message or "فشل بدء الاستضافة",
                instance=inst,
                error_contract=contract,
            )

        self._instances[instance_id] = inst
        self._save()
        return HostResult(
            ok=True,
            message=f"البوت شغال كخدمة استضافة ({inst.status})",
            instance=inst,
        )

    def stop(self, *, instance_id: str, user_id: int) -> HostResult:
        inst = self.get(instance_id, user_id=user_id)
        if inst is None:
            return HostResult(ok=False, message="المثيل غير موجود أو غير مسموح")

        try:
            stopped = False
            if inst.deployment_id:
                try:
                    from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
                        DockerProcessDriver,
                        docker_available,
                    )
                    if docker_available():
                        DockerProcessDriver().stop(inst.deployment_id)
                        stopped = True
                except Exception:
                    pass
                if not stopped:
                    from telegram_bot_engine.engines.generators.live_deployment.local_process_driver import (
                        LocalProcessDriver,
                    )
                    LocalProcessDriver().stop(inst.deployment_id)
                    stopped = True
            if not stopped and inst.pid:
                import signal
                try:
                    os.kill(inst.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        except Exception as e:
            inst.status = "stopped"
            inst.last_error = str(e)
            self._save()
            return HostResult(ok=False, message=f"تعذر الإيقاف النظيف: {e}", instance=inst)

        inst.status = "stopped"
        inst.pid = None
        self._save()
        return HostResult(ok=True, message="تم إيقاف الاستضافة", instance=inst)

    def status(self, *, user_id: int, instance_id: str | None = None) -> HostResult:
        items = self.list_for_user(user_id)
        if instance_id:
            inst = self.get(instance_id, user_id=user_id)
            if not inst:
                return HostResult(ok=False, message="المثيل غير موجود")
            # live probe + diagnose
            contract = self._diagnose_instance(inst)
            alive = self._is_alive(inst)
            if inst.status == "running" and not alive:
                inst.status = "failed"
                inst.last_error = "العملية توقفت"
                self._save()
            msg = f"الحالة الحالية: {inst.status}"
            return HostResult(ok=inst.status == "running", message=msg, instance=inst, error_contract=contract)

        if not items:
            return HostResult(ok=True, message="لا توجد مثيلات استضافة حالياً")
        lines = [f"عدد المثيلات: {len(items)}"]
        for i in items:
            lines.append(f"- `{i.instance_id}` | {i.status} | @{i.bot_username or '—'} | {i.project_path}")
        return HostResult(ok=True, message="\n".join(lines), details={"count": len(items)})

    def diagnose(self, *, user_id: int, instance_id: str) -> HostResult:
        inst = self.get(instance_id, user_id=user_id)
        if not inst:
            return HostResult(ok=False, message="المثيل غير موجود")
        contract = self._diagnose_instance(inst)
        return HostResult(
            ok=contract.ok if contract else True,
            message="تشخيص الاستضافة",
            instance=inst,
            error_contract=contract,
        )

    def _is_alive(self, inst: HostInstance) -> bool:
        """Liveness: Docker inspect for container deploys; PID only for legacy local."""
        dep = (inst.deployment_id or "").strip()
        # Docker deployments (preferred path)
        if dep.startswith("docker-") or (inst.pid is None and dep):
            try:
                from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
                    DockerProcessDriver,
                    docker_available,
                )
                if docker_available():
                    st = DockerProcessDriver().status(dep)
                    return str(getattr(st, "status", "")).lower() == "running"
            except Exception:
                pass
            # Fallback: docker inspect by deployment id / container name label
            try:
                import subprocess
                # registry may map dep_id → container name
                from telegram_bot_engine.engines.generators.live_deployment import docker_process_driver as dpd
                info = getattr(dpd, "_RUNNING", {}).get(dep) or {}
                cname = info.get("container") or info.get("name") or ""
                if cname:
                    r = subprocess.run(
                        ["docker", "inspect", "-f", "{{.State.Running}}", cname],
                        capture_output=True, text=True, timeout=5, check=False,
                    )
                    return (r.stdout or "").strip().lower() == "true"
            except Exception:
                return False
            return False
        # Legacy local subprocess path (dev only)
        if inst.pid:
            try:
                from telegram_bot_engine.engines.generators.live_deployment.local_process_driver import (
                    LocalProcessDriver,
                )
                driver = LocalProcessDriver()
                st = driver.status(dep or f"local-{inst.pid}")
                return str(getattr(st, "status", "")).lower() == "running"
            except Exception:
                try:
                    import os
                    os.kill(int(inst.pid), 0)
                    return True
                except Exception:
                    return False
        return False


    def _diagnose_instance(self, inst: HostInstance) -> ErrorContract | None:
        try:
            from ..error_intelligence import analyze_logs
        except Exception:
            return None
        run_log = ""
        install_log = ""
        # Prefer deployment log files beside project
        root = Path(inst.project_path)
        try:
            for p in sorted(root.glob(".deploy_*.run.log"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
                from bot_interface.sanitize import sanitize_log_text
                run_log = sanitize_log_text(p.read_text(encoding="utf-8", errors="ignore")[-8000:])
            for p in sorted(root.glob(".deploy_*.install.log"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
                from bot_interface.sanitize import sanitize_log_text as _slog
                install_log = _slog(p.read_text(encoding="utf-8", errors="ignore")[-5000:])
        except Exception:
            pass
        contract = analyze_logs(
            run_log=run_log,
            install_log=install_log,
            phase="run",
            extra_errors=[inst.last_error] if inst.last_error else None,
        )
        if contract.primary:
            inst.last_diagnosis = {
                "category": contract.primary.category,
                "action": contract.primary.suggested_action,
                "summary_ar": contract.primary.summary_ar,
                "package": contract.primary.suggested_package,
            }
            self._save()
        return contract


_SERVICE: HostingService | None = None


def get_hosting_service(state_dir: str | Path | None = None) -> HostingService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = HostingService(state_dir=state_dir)
    return _SERVICE
