"""
HostingService — PERMANENT_HOST plane only (long-running / commercial).

NOT the chat trial path. Trial is LiveRunner (TRIAL_CHAT).

Manages long-running bot processes for the owner:
  start / stop / status / diagnose (via Error Intelligence)

Isolation: Firecracker in production (see sandbox_runtime.select + market_gate).
State persisted under OUTPUT_DIR/hosting_state.json.
"""

from __future__ import annotations

def _cm_default_output_dir() -> str:
    try:
        from lumen.platform.paths import default_output_dir
        return default_output_dir()
    except Exception:
        from pathlib import Path as _P
        p = _P.home() / '.lumen'
        p.mkdir(parents=True, exist_ok=True)
        return str(p)


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
    sandbox_backend: str = ""  # firecracker only in production
    pid: int | None = None
    started_at: float = 0.0
    last_error: str = ""
    last_diagnosis: dict[str, Any] = field(default_factory=dict)
    token_fp: str = ""  # sha256[:16] of bot token — never store raw token
    public_base_url: str = ""  # stable ingress URL (Traefik/Caddy by name, not random port)
    webhook_public_url: str = ""  # https://…/v1/hooks/telegram/{instance_id}
    internal_port: int = 0  # logical service port for reverse-proxy (not random host map)
    platform: str = "telegram"  # telegram | discord | whatsapp
    cpu_quota: float = 0.5
    memory_mb: int = 256
    version_ref: str = ""  # git commit sha of project snapshot at deploy
    last_health_at: float = 0.0  # unix time of last successful health probe


@dataclass
class HostResult:
    ok: bool
    message: str
    instance: HostInstance | None = None
    error_contract: ErrorContract | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_user_text(self) -> str:
        """User-facing hosting result — official Telegram HTML cards."""
        from lumen.bot.telegram_text import html_bullets, html_card

        details: list[str] = []
        if self.message:
            details.append(str(self.message)[:400])
        if self.instance:
            inst = self.instance
            details.append(f"الحالة: {inst.status}")
            if inst.bot_username:
                details.append(f"البوت: @{inst.bot_username}")
            if inst.instance_id:
                details.append(f"المعرّف: {inst.instance_id}")
            if inst.pid:
                details.append(f"PID: {inst.pid}")
            if inst.project_path:
                details.append(f"المسار: {inst.project_path}")
            if inst.last_error:
                details.append(f"آخر خطأ: {inst.last_error[:200]}")
        sections: list[tuple[str, str]] = [
            ("النتيجة", html_bullets(details) if details else ("نجاح" if self.ok else "فشل")),
        ]
        if self.error_contract and self.error_contract.primary:
            sections.append(("تشخيص", self.error_contract.to_user_summary()[:800]))
        return html_card(
            "استضافة",
            sections,
            subtitle="نجاح العملية" if self.ok else "تعذّر الإكمال",
        )


class HostingService:
    """Owner-scoped hosting manager."""

    def __init__(self, state_dir: str | Path | None = None) -> None:
        base = Path(state_dir or os.getenv("OUTPUT_DIR") or _cm_default_output_dir()).resolve()
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
        """Load instance via Pydantic trust-boundary contract (HostInstanceRecord)."""
        from lumen.engine.schemas.hosting_contract import HostInstanceRecord

        return HostInstanceRecord.from_row(dict(row or {})).to_host_instance()

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
                        from lumen.engine.schemas.hosting_contract import HostInstanceRecord

                        self._store.upsert(
                            HostInstanceRecord.from_host_instance(inst).to_persist_dict()
                        )
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
            # Redis hydrate: merge instances visible to other workers
            try:
                from lumen.engine.services.hosting import redis_state as host_redis
                # Best-effort: any Redis keys we can list via user scans is limited;
                # refresh known ids from store already loaded, and accept Redis as
                # newer status if present.
                for iid, inst in list(self._instances.items()):
                    remote = host_redis.get_instance(iid)
                    if not remote:
                        continue
                    if float(remote.get("last_health_at") or 0) >= float(inst.last_health_at or 0):
                        self._instances[iid] = self._inst_from_row(remote)
            except Exception:
                pass
        except Exception:
            self._instances = {}

    def _load(self) -> None:
        try:
            with exclusive_state_lock(self._lock_path()):
                self._load_unlocked()
        except Exception:
            self._instances = {}

    def _save_unlocked(self) -> None:
        """Persist each instance after Pydantic contract validation (trust boundary)."""
        from lumen.engine.schemas.hosting_contract import HostInstanceRecord
        from lumen.engine.services.hosting import redis_state as host_redis

        for inst in self._instances.values():
            record = HostInstanceRecord.from_host_instance(inst)
            payload = record.to_persist_dict()
            self._store.upsert(payload)
            try:
                ok_r = host_redis.put_instance(payload)
                if ok_r is False:
                    # put returned False = Redis unavailable in allowed-dev skip
                    env = (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").lower()
                    multi = (os.environ.get("TBE_MULTI_TENANT") or "1").strip().lower() in {
                        "1", "true", "yes", "on",
                    }
                    if multi and env not in {"dev", "development", "local", "test"}:
                        raise RuntimeError(
                            "host_redis_put_failed: REDIS_URL required for durable host state in production"
                        )
            except RuntimeError:
                raise
            except Exception as exc:
                env = (os.environ.get("ENVIRONMENT") or os.environ.get("TBE_ENV") or "").lower()
                if env not in {"dev", "development", "local", "test"}:
                    raise RuntimeError(f"host_redis_put_error:{type(exc).__name__}") from exc

    def _save(self) -> None:
        with exclusive_state_lock(self._lock_path()):
            self._save_unlocked()

    def list_for_user(self, user_id: int) -> list[HostInstance]:
        out = {i.instance_id: i for i in self._instances.values() if i.user_id == user_id}
        try:
            from lumen.engine.services.hosting import redis_state as host_redis
            for remote in host_redis.list_for_user(int(user_id)):
                iid = str(remote.get("instance_id") or "")
                if not iid:
                    continue
                inst = self._inst_from_row(remote)
                out[iid] = inst
                self._instances[iid] = inst
        except Exception:
            pass
        return list(out.values())

    def get(self, instance_id: str, user_id: int | None = None) -> HostInstance | None:
        inst = self._instances.get(instance_id)
        if inst is None:
            try:
                from lumen.engine.services.hosting import redis_state as host_redis
                remote = host_redis.get_instance(str(instance_id))
                if remote:
                    inst = self._inst_from_row(remote)
                    self._instances[str(instance_id)] = inst
            except Exception:
                inst = None
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
        entry_point: str = "",
    ) -> HostResult:
        path = Path(project_path).resolve()
        if not path.is_dir():
            return HostResult(ok=False, message="مسار المشروع غير موجود")

        # Containment: must live under THIS user's sandbox (IDOR root fix).
        # API layer already checks tenant sandbox; HostService enforces the same
        # invariant so internal callers cannot host another tenant's tree.
        try:
            from lumen.engine.services.user_sandbox import get_user_sandbox
            sandbox = get_user_sandbox(int(user_id), self.output_root)
            if not sandbox.is_under_sandbox(path):
                return HostResult(ok=False, message="مسار المشروع خارج مساحة عزل المستخدم")
            try:
                from lumen.engine.services.disk_quota import enforce_user_quota
                enforce_user_quota(sandbox.root, user_id=int(user_id))
            except RuntimeError as exc:
                return HostResult(ok=False, message=f"حصة التخزين ممتلئة: {exc}")
        except Exception:
            return HostResult(ok=False, message="مسار المشروع خارج مساحة العزل")


        # ── Production / scale foundation gates ──────────────────────────
        try:
            from lumen.engine.services.isolation_policy import (
                decide_isolation,
                is_dev_environment,
                strong_sandbox_available,
            )
            decision = decide_isolation()
            if decision.require_strong_isolation:
                ok_sbx, sbx_reason = strong_sandbox_available()
                if not ok_sbx:
                    return HostResult(
                        ok=False,
                        message=(
                            "الاستضافة تتطلب عزل Firecracker (microVM). "
                            f"غير متاح: {sbx_reason[:240]}"
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
                # Egress network required for container backends; Firecracker uses TAP/netns instead
                backend_pref = (os.environ.get("TBE_SANDBOX_BACKEND") or "auto").strip().lower()
                if backend_pref not in {"firecracker"} and not (
                    os.environ.get("TBE_DOCKER_NETWORK") or ""
                ).strip():
                    # auto may still pick firecracker — only hard-require docker net if FC not preferred
                    if backend_pref in {"docker", "dind", "gvisor"}:
                        return HostResult(
                            ok=False,
                            message="TBE_DOCKER_NETWORK مطلوب في الإنتاج (شبكة محدودة الخروج).",
                        )
        except Exception as gate_exc:
            return HostResult(ok=False, message=f"فشل بوابة الاستضافة: {gate_exc}")


        # Commercial market gate — refuse to sell weak hosting
        try:
            from lumen.engine.services.hosting.market_gate import evaluate_market_gate
            gate = evaluate_market_gate()
            if not gate.ok:
                return HostResult(ok=False, message=gate.message_ar())
        except Exception as gate_exc:
            return HostResult(ok=False, message=f"فشل بوابة السوق: {gate_exc}")

        from lumen.engine.services.hosting.contract import token_fingerprint

        token_norm = (bot_token or "").strip()
        token_fp = token_fingerprint(token_norm)

        # Part 1 — real server run: resolve entry + install deps on host (has network)
        from lumen.engine.services.hosting.prepare_runtime import prepare_project_for_host

        prepared = prepare_project_for_host(path, entry_point=entry_point or "")
        if not prepared.ok:
            return HostResult(
                ok=False,
                message=prepared.message or "فشل تجهيز المشروع للتشغيل على السيرفر",
                details=dict(prepared.details or {}),
            )
        entry_resolved = prepared.entry_point
        version_ref = str((prepared.details or {}).get("version_ref") or "")
        try:
            if version_ref:
                from lumen.engine.services.hosting.versions import publish_version
                publish_version(path, version_ref)
        except Exception:
            pass

        # ── Scale mode (20k path): enqueue for workers, never block API on docker build ──
        scale = (os.environ.get("TBE_SCALE_MODE") or "").strip().lower() in {"1", "true", "yes", "on"}
        multi = (os.environ.get("TBE_MULTI_TENANT") or "1").strip().lower() in {"1", "true", "yes", "on"}
        if scale or (os.environ.get("TBE_FORCE_QUEUE") or "0").strip().lower() in {"1", "true", "yes", "on"}:
            try:
                from lumen.engine.services.hosting.deploy_queue import get_deploy_queue
                from lumen.engine.services.hosting.capacity import estimate_nodes_for, local_node_capacity
                q = get_deploy_queue()
                # Pro plan bot limit (resolved from entitlement, FAIL-CLOSED)
                # If the entitlement resolver throws we block the enqueue instead
                # of falling back to a high env default (50) that would let a Pro
                # user exceed their 3-bot limit.
                try:
                    from lumen.bot.ui.pro_plan_entitlement import resolve_plan_limits
                    max_bots = resolve_plan_limits(int(user_id)).max_bots
                except Exception:
                    logger.warning("pro plan bot-limit resolve FAILED (fail-closed) uid=%s", user_id, exc_info=True)
                    return HostResult(
                        ok=False,
                        message="تعذر التحقق من حدود الاشتراك حالياً. حاول مرة أخرى بعد لحظات.",
                    )
                running_u = 0
                if hasattr(q, "count_running_for_user"):
                    running_u = int(q.count_running_for_user(int(user_id)))
                else:
                    running_u = sum(1 for i in self.list_for_user(int(user_id)) if i.status == "running")
                if running_u >= max_bots:
                    return HostResult(ok=False, message=f"وصلت للحد الأقصى ({max_bots}) بوت مستضاف لحسابك.")
                # Portable artifact so ANY worker node can build (not only this host's disk)
                from lumen.engine.services.hosting.artifacts import package_project, publish_artifact
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
                        "entry_point": entry_resolved,
                        "artifact_uri": artifact_uri,
                        "artifact_sha256": digest,
                        "artifact_job_key": pre_id,
                        "prepare": dict(prepared.details or {}),
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
                        f"`python -m lumen.engine.services.hosting.worker`\n"
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

        # Host rate limits (concurrent + starts/hour)
        try:
            from lumen.engine.services.hosting.rate_limiter import check_can_start, record_start
            running_n = sum(1 for i in self.list_for_user(int(user_id)) if i.status == "running")

            # ── Pro plan bot limit enforcement (FAIL-CLOSED) ──
            # If the entitlement resolver throws (Redis down, import error, etc.)
            # we must NOT fall through to check_can_start (which uses a higher
            # env default).  Instead we block the start so a Pro user can never
            # exceed their plan limit due to an infrastructure hiccup.
            try:
                from lumen.bot.ui.pro_plan_entitlement import resolve_plan_limits
                _limits = resolve_plan_limits(int(user_id))
                if running_n >= _limits.max_bots:
                    return HostResult(
                        ok=False,
                        message=(
                            f"وصلت إلى الحد الأقصى ({_limits.max_bots}) بوت مستضاف لحسابك."
                            + (" — اشترك في Lumen Pro لاستضافة حتى 3 بوتات." if not _limits.is_pro else "")
                        ),
                    )
            except Exception:
                logger.warning("pro plan bot-limit check FAILED (fail-closed) uid=%s", user_id, exc_info=True)
                return HostResult(
                    ok=False,
                    message="تعذر التحقق من حدود الاشتراك حالياً. حاول مرة أخرى بعد لحظات.",
                )

            ok_rl, reason_rl = check_can_start(user_id=int(user_id), running_count=running_n)
            if not ok_rl:
                return HostResult(ok=False, message=f"حد الاستضافة: {reason_rl}")
        except Exception as rl_exc:
            env = (os.environ.get("ENVIRONMENT") or "").lower()
            if env not in {"dev", "development", "local", "test"}:
                return HostResult(ok=False, message=f"rate_limit_unavailable:{type(rl_exc).__name__}")

        # Webhook vs polling: clear only when forced to polling
        try:
            from lumen.bot.singleton import clear_telegram_webhook
            mode = (os.environ.get("TBE_HOST_WEBHOOK_MODE") or "auto").strip().lower()
            if mode in {"0", "false", "no", "off", "polling"}:
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

        # Isolation: sandbox_runtime ONLY — no LocalProcess fallback
        try:
            from lumen.engine.services.live_deployment.token_validator import (
                TokenValidator,
            )
        except Exception as e:
            return HostResult(ok=False, message=f"تعذر تحميل محرك الاستضافة: {e}")

        tv = TokenValidator().validate(bot_token)
        if not getattr(tv, "valid", False):
            msg = getattr(tv, "error", None) or "توكن غير صالح"
            return HostResult(ok=False, message=f"التوكن غير صالح: {msg}")

        username = bot_username or getattr(tv, "bot_username", "") or ""
        env = {
            "TELEGRAM_BOT_TOKEN": bot_token,
            "BOT_TOKEN": bot_token,
        }
        env.update({k: str(v) for k, v in (prepared.env_vars or {}).items() if k and v is not None})
        try:
            from lumen.engine.services.hosting.orchestration import start_host as _orch_start
            from lumen.engine.services.hosting.secrets_env import inject_secrets_env, seal_project_secrets
            try:
                seal_project_secrets(path, {"BOT_TOKEN": token_norm, "TELEGRAM_BOT_TOKEN": token_norm})
            except Exception:
                pass
            _env = inject_secrets_env(path, env)
            _backend, handle = _orch_start(
                project_path=str(path),
                bot_token=token_norm,
                user_id=int(user_id),
                service_name=f"host-u{user_id}",
                env_vars=_env,
            )
        except Exception as sbx_exc:
            return HostResult(
                ok=False,
                message=f"عزل الاستضافة مرفوض (sandbox_runtime): {type(sbx_exc).__name__}: {sbx_exc}"[:500],
            )
        dep_id = handle.deployment_id or ""
        st = handle.status or ""
        message = handle.message or ""
        backend_name = getattr(_backend, "name", "") or str((handle.meta or {}).get("backend") or "")
        if not handle.ok:
            return HostResult(
                ok=False,
                message=f"فشل تشغيل الصندوق المعزول ({backend_name}): {message[:300]}",
                details={"backend": backend_name, "meta": dict(handle.meta or {})},
            )
        # Production / multi-tenant: Firecracker only — never accept weak backends
        try:
            from lumen.engine.services.sandbox_runtime.select import is_production_sandbox_path
            if is_production_sandbox_path() and backend_name != "firecracker":
                return HostResult(
                    ok=False,
                    message=(
                        f"مسار الإنتاج يرفض backend={backend_name}. "
                        "الاستضافة التجارية تتطلب Firecracker microVM فقط."
                    ),
                    details={"backend": backend_name},
                )
        except Exception:
            pass
        # Permanent host: refuse "running" without bot health when FC reports meta
        meta = dict(handle.meta or {})
        if backend_name == "firecracker" and meta.get("bot_healthy") is False and meta.get("claim", "").endswith("failed"):
            return HostResult(
                ok=False,
                message=f"الاستضافة الدائمة رُفضت: صحة البوت داخل الضيف غير مؤكدة ({message[:200]})",
                details={"backend": backend_name, "meta": meta},
            )
        import re as _re
        import uuid
        pid = None
        m_pid = _re.search(r"pid=(\d+)", message)
        if m_pid:
            pid = int(m_pid.group(1))
        elif isinstance(handle.meta, dict) and handle.meta.get("pid"):
            try:
                pid = int(handle.meta.get("pid"))
            except (TypeError, ValueError):
                pid = None

        instance_id = f"host-{uuid.uuid4().hex[:10]}"
        running_like = st in ("running", "deploy_running") or "running" in st.lower()
        failed_like = "fail" in st.lower()
        from lumen.engine.services.hosting.ingress import (
            public_url_for_instance,
            write_traefik_route,
        )
        public_url = public_url_for_instance(instance_id)
        try:
            write_traefik_route(instance_id=instance_id, enabled=running_like)
            from lumen.engine.services.hosting.ingress import write_caddy_route
            write_caddy_route(instance_id=instance_id, enabled=running_like)
        except Exception:
            pass
        version_ref = str((prepared.details or {}).get("version_ref") or "")
        inst = HostInstance(
            instance_id=instance_id,
            user_id=user_id,
            project_path=str(path),
            entry_point=entry_resolved or "",
            bot_username=username,
            status="running" if running_like else ("failed" if failed_like else (st or "unknown")),
            deployment_id=str(dep_id),
            sandbox_backend=str(backend_name or ""),
            pid=pid,
            started_at=time.time(),
            last_error="" if not failed_like else message,
            token_fp=token_fp,
            public_base_url=public_url,
            webhook_public_url="",  # filled below
            internal_port=0,
            version_ref=version_ref,
            last_health_at=time.time() if running_like else 0.0,
        )
        # Stable logical port for reverse-proxy backends (deterministic, not random host map)
        try:
            import hashlib
            h = int(hashlib.sha256(instance_id.encode()).hexdigest()[:6], 16)
            inst.internal_port = 8000 + (h % 1000)  # 8000–8999
        except Exception:
            inst.internal_port = 8080
        # Resources from capacity defaults — Pro plan aware
        try:
            from lumen.hosting.project_manifest import default_resources_for_user
            _res = default_resources_for_user(int(user_id or 0))
            inst.cpu_quota = float(_res.cpu)
            inst.memory_mb = int(_res.memory_mb)
        except Exception:
            inst.cpu_quota = 0.5
            inst.memory_mb = 256
        inst.platform = "telegram"

        # Normalize status using known constants
        try:
            from lumen.engine.services.live_deployment.report_data import (
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
        try:
            from lumen.engine.services.hosting.rate_limiter import record_start
            record_start(int(user_id))
        except Exception:
            pass
        try:
            from lumen.engine.services.hosting.secrets_env import seal_project_secrets
            seal_project_secrets(path, {"BOT_TOKEN": token_norm, "TELEGRAM_BOT_TOKEN": token_norm})
        except Exception:
            pass
        try:
            from lumen.hosting.project_space import ensure_project_space, register_space_index
            sp = ensure_project_space(path, user_id=int(user_id))
            register_space_index(sp)
        except Exception:
            pass

        # Webhook manager + gateway routes + project manifest (architecture plane)
        try:
            from lumen.hosting.webhook_manager import apply_to_instance
            from lumen.hosting.gateway import write_routes_for_instance
            from lumen.hosting.project_manifest import write_manifest_for_instance
            apply_to_instance(instance_id=instance_id, bot_token=token_norm, inst=inst)
            write_routes_for_instance(instance_id, enabled=(inst.status == "running"))
            write_manifest_for_instance(inst)
            self._save()
        except Exception:
            logger.exception("architecture plane (webhook/gateway/manifest) failed")
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
            dep = (inst.deployment_id or "").strip()
            # Permanent host plane: stop via Firecracker only (no Docker fallback)
            if dep:
                try:
                    from lumen.engine.services.sandbox_runtime.firecracker_backend import (
                        FirecrackerSandboxBackend,
                    )
                    FirecrackerSandboxBackend().stop(dep)
                    stopped = True
                except Exception as fc_exc:
                    inst.last_error = f"fc_stop:{type(fc_exc).__name__}:{fc_exc}"[:300]
        except Exception as e:
            inst.status = "stopped"
            inst.last_error = str(e)
            self._save()
            return HostResult(ok=False, message=f"تعذر الإيقاف النظيف: {e}", instance=inst)

        inst.status = "stopped"
        inst.pid = None
        try:
            from lumen.engine.services.hosting.usage_billing import settle_instance
            settle_instance(inst)
        except Exception:
            pass
        try:
            from lumen.hosting.gateway import remove_routes_for_instance
            remove_routes_for_instance(inst.instance_id)
        except Exception:
            pass
        try:
            from lumen.engine.services.hosting.backup_manager import backup_project
            backup_project(inst.project_path, instance_id=inst.instance_id)
        except Exception:
            pass
        self._save()
        return HostResult(ok=True, message="تم إيقاف الاستضافة", instance=inst)

    def restart(
        self,
        *,
        instance_id: str,
        user_id: int,
        bot_token: str = "",
    ) -> HostResult:
        """Stop then start. Token optional if sealed secrets exist on project."""
        inst = self.get(instance_id, user_id=user_id)
        if inst is None:
            return HostResult(ok=False, message="المثيل غير موجود أو غير مسموح")
        path = inst.project_path
        entry = getattr(inst, "entry_point", "") or ""
        username = inst.bot_username or ""
        token = (bot_token or "").strip()
        if not token:
            try:
                from lumen.hosting.secrets_env import load_project_secrets
                sealed = load_project_secrets(path)
                token = (sealed.get("BOT_TOKEN") or sealed.get("TELEGRAM_BOT_TOKEN") or "").strip()
            except Exception:
                token = ""
        if not token or ":" not in token:
            return HostResult(
                ok=False,
                message="إعادة التشغيل تحتاج توكن — أرسل التوكن أو تأكد من وجود أسرار مشفّرة للمشروع",
                instance=inst,
            )
        self.stop(instance_id=instance_id, user_id=user_id)
        result = self.start(
            user_id=user_id,
            project_path=path,
            bot_token=token,
            bot_username=username,
            entry_point=entry,
        )
        # Lifecycle: keep stable instance_id for the user-facing project identity
        if result.ok and result.instance is not None:
            new_inst = result.instance
            old_id = instance_id
            if new_inst.instance_id != old_id:
                self._instances.pop(new_inst.instance_id, None)
                new_inst.instance_id = old_id
                self._instances[old_id] = new_inst
                try:
                    self._save()
                except Exception:
                    pass
                result.instance = new_inst
        return result

    def redeploy(
        self,
        *,
        instance_id: str,
        user_id: int,
        bot_token: str = "",
    ) -> HostResult:
        """One-shot: re-prepare project (deps/version) then restart same instance_id."""
        inst = self.get(instance_id, user_id=user_id)
        if inst is None:
            return HostResult(ok=False, message="المثيل غير موجود أو غير مسموح")
        try:
            from lumen.engine.services.hosting.prepare_runtime import prepare_project_for_host
            prep = prepare_project_for_host(
                inst.project_path,
                entry_point=getattr(inst, "entry_point", "") or "",
            )
            if not prep.ok:
                return HostResult(ok=False, message=f"فشل تجهيز إعادة النشر: {prep.message}", instance=inst)
            if prep.entry_point:
                inst.entry_point = prep.entry_point
            if prep.details.get("version_ref"):
                inst.version_ref = str(prep.details.get("version_ref") or "")
        except Exception as exc:
            return HostResult(
                ok=False,
                message=f"redeploy_prepare:{type(exc).__name__}",
                instance=inst,
            )
        return self.restart(instance_id=instance_id, user_id=user_id, bot_token=bot_token)

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
                inst.last_error = "الاستضافة توقفت أو البوت داخل الضيف غير مؤكد"
                self._save()
            health = "bot_ok" if alive else "bot_down_or_unconfirmed"
            msg = f"الحالة الحالية: {inst.status} | صحة: {health}"
            return HostResult(ok=inst.status == "running" and alive, message=msg, instance=inst, error_contract=contract)

        if not items:
            return HostResult(ok=True, message="لا توجد مثيلات استضافة حالياً")
        lines = [f"عدد المثيلات: {len(items)}"]
        for i in items:
            lines.append(f"- `{i.instance_id}` | {i.status} | @{i.bot_username or '—'} | {i.project_path}")
        return HostResult(ok=True, message="\n".join(lines), details={"count": len(items)})


    def logs(self, *, user_id: int, instance_id: str, limit: int = 80) -> HostResult:
        """Return recent sandbox/run logs for an instance (sanitized)."""
        inst = self.get(instance_id, user_id=user_id)
        if inst is None:
            return HostResult(ok=False, message="المثيل غير موجود أو غير مسموح")
        lines: list[str] = []
        dep = (inst.deployment_id or "").strip()
        backend = (getattr(inst, "sandbox_backend", None) or "").strip().lower()
        try:
            from lumen.bot.sanitize import sanitize_log_text
            if backend == "firecracker" or dep.startswith("fc-") or dep:
                from lumen.engine.services.hosting.log_aggregator import (
                    collect_instance_logs,
                    ship_to_loki,
                )
                raw = collect_instance_logs(inst.instance_id, dep, limit=max(10, min(200, int(limit))), project_path=str(inst.project_path or ""))
                lines = [sanitize_log_text(str(x)) for x in (raw or [])]
                try:
                    ship_to_loki(inst.instance_id, lines)
                except Exception:
                    pass
            elif dep:
                from lumen.engine.services.sandbox_runtime.firecracker_backend import FirecrackerSandboxBackend
                b = FirecrackerSandboxBackend()
                raw = b.logs(dep, limit=max(10, min(200, int(limit))))
                lines = [sanitize_log_text(str(x)) for x in (raw or [])]
        except Exception as exc:
            return HostResult(
                ok=False,
                message=f"تعذّر قراءة السجلات: {type(exc).__name__}",
                instance=inst,
            )
        # Fallback: project deploy log files
        if not lines:
            try:
                from lumen.bot.sanitize import sanitize_log_text as _slog
                root = Path(inst.project_path)
                for pth in sorted(root.glob(".deploy_*.run.log"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
                    chunk = _slog(pth.read_text(encoding="utf-8", errors="ignore")[-6000:])
                    lines = chunk.splitlines()[-int(limit):]
            except Exception:
                pass
        if not lines:
            return HostResult(
                ok=True,
                message="لا سجلات متاحة بعد لهذا المثيل.",
                instance=inst,
                details={"log_lines": []},
            )
        body = "\n".join(lines[-int(limit):])
        return HostResult(
            ok=True,
            message=body[:3500],
            instance=inst,
            details={"log_lines": lines[-int(limit):], "line_count": len(lines)},
        )

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
        """Liveness via sandbox backend matching deployment_id prefix."""
        dep = (inst.deployment_id or "").strip()
        if not dep:
            return False
        backend = (getattr(inst, "sandbox_backend", None) or "").strip().lower()
        # Firecracker microVMs
        if backend == "firecracker" or dep.startswith("fc-"):
            try:
                from lumen.engine.services.sandbox_runtime.firecracker_backend import (
                    FirecrackerSandboxBackend,
                )
                st = FirecrackerSandboxBackend().status(dep)
                if str(st.status).lower() != "running":
                    return False
                # Permanent host: VMM alone is not enough — need bot marker
                meta = dict(getattr(st, "meta", None) or {})
                return bool(meta.get("bot_marker") or meta.get("bot_healthy"))
            except Exception:
                return False
        # Permanent host plane: no Docker liveness — Firecracker only
        return False


    def _diagnose_instance(self, inst: HostInstance) -> ErrorContract | None:
        try:
            from ..error_intelligence import analyze_logs
        except Exception:
            return None
        run_log = ""
        install_log = ""
        # Firecracker / sandbox backend logs first
        dep = (inst.deployment_id or "").strip()
        backend = (getattr(inst, "sandbox_backend", None) or "").strip().lower()
        try:
            from lumen.bot.sanitize import sanitize_log_text
            if backend == "firecracker" or dep.startswith("fc-"):
                from lumen.engine.services.sandbox_runtime.firecracker_backend import (
                    FirecrackerSandboxBackend,
                )
                lines = FirecrackerSandboxBackend().logs(dep, limit=200)
                run_log = sanitize_log_text("\n".join(lines)[-8000:])
            elif dep:
                from lumen.engine.services.sandbox_runtime.firecracker_backend import (
                    FirecrackerSandboxBackend,
                )
                lines = FirecrackerSandboxBackend().logs(dep, limit=200)
                if lines:
                    run_log = sanitize_log_text("\n".join(lines)[-8000:])
        except Exception:
            pass
        # Prefer deployment log files beside project
        root = Path(inst.project_path)
        try:
            if not run_log:
                for p in sorted(root.glob(".deploy_*.run.log"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
                    from lumen.bot.sanitize import sanitize_log_text
                    run_log = sanitize_log_text(p.read_text(encoding="utf-8", errors="ignore")[-8000:])
            for p in sorted(root.glob(".deploy_*.install.log"), key=lambda x: x.stat().st_mtime, reverse=True)[:1]:
                from lumen.bot.sanitize import sanitize_log_text as _slog
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
        try:
            from lumen.engine.services.hosting.health_monitor import start_background
            start_background(lambda: _SERVICE)
        except Exception:
            pass
        try:
            from lumen.engine.services.hosting.ops_scheduler import start_ops_scheduler
            start_ops_scheduler(lambda: _SERVICE)
        except Exception:
            pass
    return _SERVICE
