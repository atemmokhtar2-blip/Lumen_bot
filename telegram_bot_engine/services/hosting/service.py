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
        base = Path(state_dir or os.getenv("OUTPUT_DIR", "/tmp/generated"))
        self.state_dir = base / "hosting"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.state_dir / "instances.json"
        self._instances: dict[str, HostInstance] = {}
        self._load()

    def _load(self) -> None:
        if not self.state_file.exists():
            return
        try:
            data = json.loads(self.state_file.read_text(encoding="utf-8"))
            for row in data.get("instances", []):
                inst = HostInstance(**{
                    k: v for k, v in row.items()
                    if k in HostInstance.__dataclass_fields__
                })
                self._instances[inst.instance_id] = inst
        except Exception:
            self._instances = {}

    def _save(self) -> None:
        payload = {
            "instances": [asdict(i) for i in self._instances.values()],
            "updated_at": time.time(),
        }
        self.state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

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

        # Containment: must live under OUTPUT_DIR (never host system paths)
        try:
            out_root = Path(os.getenv("OUTPUT_DIR", "/tmp/generated")).resolve()
            path.relative_to(out_root)
        except Exception:
            return HostResult(ok=False, message="مسار المشروع خارج مساحة العزل")

        # Stop existing instance for same path+user OR same token (409 Conflict)
        import hashlib
        token_norm = (bot_token or "").strip()
        token_fp = hashlib.sha256(token_norm.encode()).hexdigest()[:16] if token_norm else ""
        for inst in list(self.list_for_user(user_id)):
            same_path = Path(inst.project_path).resolve() == path and inst.status == "running"
            same_token = (
                inst.status == "running"
                and token_fp
                and (getattr(inst, "token_fp", "") or "") == token_fp
            )
            if same_path or same_token:
                self.stop(instance_id=inst.instance_id, user_id=user_id)

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

        # Isolation: Docker required in SaaS (local only with explicit opt-in)
        try:
            from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
                DockerProcessDriver,
                docker_available,
            )
            from telegram_bot_engine.engines.generators.live_deployment.local_process_driver import (
                LocalProcessDriver,
            )
            from telegram_bot_engine.engines.generators.live_deployment.token_validator import (
                TokenValidator,
            )
        except Exception as e:
            return HostResult(ok=False, message=f"تعذر تحميل محرك الاستضافة: {e}")

        tv = TokenValidator().validate(bot_token)
        if not getattr(tv, "valid", False):
            msg = getattr(tv, "error", None) or "توكن غير صالح"
            return HostResult(ok=False, message=f"التوكن غير صالح: {msg}")

        username = bot_username or getattr(tv, "bot_username", "") or ""
        require_docker = (os.environ.get("TBE_REQUIRE_DOCKER") or "0").strip().lower() in {
            "1", "true", "yes", "on",
        }
        allow_local = (os.environ.get("TBE_ALLOW_LOCAL_PROCESS") or "1").strip().lower() not in {
            "0", "false", "no", "off",
        }
        if docker_available():
            driver = DockerProcessDriver()
        elif require_docker and not allow_local:
            return HostResult(
                ok=False,
                message="Docker مطلوب لاستضافة آمنة وغير متاح على هذا الخادم",
            )
        else:
            driver = LocalProcessDriver()
        env = {
            "TELEGRAM_BOT_TOKEN": bot_token,
            "BOT_TOKEN": bot_token,
            "TOKEN": bot_token,
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
        if not inst.pid:
            # ask driver if possible
            try:
                from telegram_bot_engine.engines.generators.live_deployment.local_process_driver import (
                    LocalProcessDriver,
                )
                driver = LocalProcessDriver()
                if inst.deployment_id and hasattr(driver, "status"):
                    st = driver.status(inst.deployment_id)
                    s = getattr(st, "status", "") or ""
                    return "run" in s.lower()
            except Exception:
                return inst.status == "running"
            return inst.status == "running"
        try:
            os.kill(inst.pid, 0)
            return True
        except OSError:
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
                run_log = p.read_text(encoding="utf-8", errors="ignore")[-8000:]
            for p in sorted(root.glob(".deploy_*.install.log"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
                install_log = p.read_text(encoding="utf-8", errors="ignore")[-5000:]
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
