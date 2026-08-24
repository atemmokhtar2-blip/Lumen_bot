"""
LiveRunner — real dependency install + bot process execution + error capture.

Install strategy (robust):
  1) try venv + ensure pip works
  2) if venv/pip broken → pip install --target .tbe_deps (isolated)
  3) surface real pip ERROR lines to the user (no opaque "pip install failed")
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import ast



from .report import LiveRunReport
from .telegram_api import (
    validate_telegram_token,
    _is_transient_telegram_failure,
    _delete_telegram_webhook,
)
from .runtime_bootstrap import (
    _find_requirements,
    _find_entry,
    _ensure_runtime,
    _venv_python,
    _deps_dir,
)
from .requirements_pip import (
    _sanitize_requirements,
    _pip_install,
    _extract_errors,
    _extract_missing_modules,
    _preflight_ensure_deps,
    _ensure_packages_in_requirements,
    _module_to_package,
    _error_location_summary,
    _pip_install_packages_direct,
    _resolve_missing_via_source,
    _preemptive_loosen,
    _conflict_packages_from_log,
    _loosen_requirements,
    _unpin_all_hard_pins,
)
from .project_patch import (
    _write_project_env,
    _inject_entry_bootstrap,
    _patch_getenv_token_defaults,
    _patch_hardcoded_tokens,
    _smart_auto_heal,
)

class LiveRunnerService:
    def run(
        self,
        project_path: str | Path,
        bot_token: str,
        entry_hint: str | None = None,
        run_seconds: float = float(__import__('os').environ.get('LIVE_RUN_SECONDS', 900)),
        install: bool = True,
        max_heal_rounds: int = 5,
    ) -> LiveRunReport:
        """
        Real install + run with Auto-Heal for missing dependencies.

        On ModuleNotFoundError / ImportError:
          1) map module → package
          2) append to requirements.txt if missing
          3) reinstall + rerun  (up to max_heal_rounds)
        """
        t0 = time.perf_counter()
        # Host-process execution permanently disabled (Docker-only production rule).
        return LiveRunReport(
            ok=False,
            phase="security",
            message="LiveRunner host process removed — Docker isolation required",
            errors=["host_process_removed", "docker_required"],
            duration_ms=0.0,
        )
        # unreachable legacy gate
        try:
            from telegram_bot_engine.services.isolation_policy import assert_local_process_allowed
            assert_local_process_allowed()
        except RuntimeError as exc:
            return LiveRunReport(
                ok=False,
                phase="security",
                message=f"التشغيل المحلي مرفوض: {exc}",
                errors=["local_process_denied"],
                duration_ms=0.0,
            )

        root = Path(project_path).resolve()
        if not root.exists():
            return LiveRunReport(ok=False, phase="validate", message="مسار المشروع غير موجود")
        try:
            from telegram_bot_engine.services.safe_fs import assert_no_symlinks_in_path
            assert_no_symlinks_in_path(root)
        except Exception as _sym_exc:
            return LiveRunReport(
                ok=False,
                phase="security",
                message=f"project_path_symlink_forbidden:{type(_sym_exc).__name__}",
                errors=["symlink_forbidden"],
                duration_ms=0.0,
            )

        # Refuse to poll with the platform bot token — causes 409 Conflict
        # and takes down the SaaS bot for every user.
        platform_tok = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
        user_tok = (bot_token or "").strip()
        if platform_tok and user_tok and platform_tok == user_tok:
            return LiveRunReport(
                ok=False,
                phase="validate",
                message=(
                    "لا تستخدم توكن المنصة للبوت المولَّد. "
                    "أنشئ بوت جديد من @BotFather والصق التوكن الخاص به فقط."
                ),
                errors=["platform_token_forbidden"],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        # Always clear webhook before child polling (avoids 409 Conflict)
        try:
            _delete_telegram_webhook(user_tok)
        except Exception:
            pass

        ok, me, err = validate_telegram_token(bot_token)
        soft_continue = (os.environ.get("TELEGRAM_VALIDATE_SOFT") or "1").strip().lower() in {
            "1", "true", "yes", "on",
        }
        preflight_warnings: list[str] = []
        if not ok:
            # Token format already validated inside validate_telegram_token.
            # On transient Telegram 502/503, optionally continue install+run
            # so a temporary Telegram outage does not block the user entirely.
            is_transient = bool((me or {}).get("transient")) or (
                "غير مستقر مؤقتًا" in (err or "") or "502" in (err or "") or "503" in (err or "")
            )
            if not (soft_continue and is_transient):
                return LiveRunReport(
                    ok=False, phase="validate", message=err, errors=[err],
                    duration_ms=(time.perf_counter() - t0) * 1000,
                )
            # Soft path: proceed without bot username; warn the user
            me = me if isinstance(me, dict) else {}
            preflight_warnings.append(
                "telegram_api_transient: continued despite getMe 502/503 — "
                "Telegram gateway was unstable; bot may still start"
            )
        username = (me or {}).get("username") or ""
        bot_id = (me or {}).get("id")

        entry = _find_entry(root, [entry_hint] if entry_hint else None)
        if entry is None:
            return LiveRunReport(
                ok=False, phase="validate",
                message="لم أجد نقطة دخول قابلة للتشغيل (main.py/bot.py/…)",
                bot_username=username, bot_id=bot_id, errors=["no_entry_point"],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        # Auto-repair common source syntax issues (e.g. \\' written literally)
        from ..source_fix import repair_project_sources, discover_token_env_names, syntax_check_entry
        repair_notes = list(preflight_warnings) + repair_project_sources(root)
        # Proactive: clear webhook + inject token so polling bots start cleanly
        try:
            ok_wh, wh_msg = _delete_telegram_webhook(bot_token)
            repair_notes.append(f"preflight_webhook:{'ok' if ok_wh else 'fail'}:{wh_msg}")
        except Exception as e:
            repair_notes.append(f"preflight_webhook_err:{type(e).__name__}")
        try:
            from ..source_fix import discover_token_env_names as _disc
            repair_notes.append(_write_project_env(root, bot_token, _disc(root)))
            repair_notes.extend(_patch_hardcoded_tokens(root, bot_token)[:8])
            repair_notes.append(_inject_entry_bootstrap(entry, bot_token))
        except Exception as e:
            repair_notes.append(f"preflight_token_inject:{type(e).__name__}")

        ok_syn, syn_err = syntax_check_entry(entry)
        if not ok_syn:
            return LiveRunReport(
                ok=False, phase="validate",
                message=f"SyntaxError في `{entry.name}` بعد محاولة الإصلاح: {syn_err}",
                bot_username=username, bot_id=bot_id,
                errors=[syn_err] + repair_notes[:5],
                duration_ms=(time.perf_counter() - t0) * 1000,
                details={"repair_notes": repair_notes},
            )

        # Pre-flight: AST-scan imports and ensure third-party packages are listed
        preflight_added: list[str] = []
        try:
            preflight_added = _preflight_ensure_deps(root)
        except Exception:
            preflight_added = []

        heal_notes: list[str] = list(preflight_added)
        if preflight_added:
            heal_notes = [f"preflight:{p}" for p in preflight_added]
        all_install_log = ""
        last_report: LiveRunReport | None = None

        for heal_round in range(max_heal_rounds + 1):
            report = self._attempt_install_and_run(
                root=root,
                entry=entry,
                bot_token=bot_token,
                username=username,
                bot_id=bot_id,
                run_seconds=run_seconds,
                install=install,
                repair_notes=repair_notes,
                t0=t0,
                heal_notes=heal_notes,
            )
            last_report = report
            all_install_log = (all_install_log + "\n" + (report.install_log or "")).strip()

            if report.ok:
                if heal_notes:
                    report.details = dict(report.details or {})
                    report.details["auto_healed_packages"] = list(heal_notes)
                    report.warnings = list(report.warnings or []) + [
                        f"auto_healed: {', '.join(heal_notes)}"
                    ]
                    report.message = (
                        report.message
                        + f" | تم إصلاح تبعيات ناقصة تلقائياً: {', '.join(heal_notes)}"
                    )
                report.install_log = all_install_log[-4000:]
                return report

            # ── Error Intelligence is the single decision authority ──
            if report.phase not in ("run", "install"):
                return report

            try:
                from ..error_intelligence import analyze_logs
            except Exception:
                analyze_logs = None  # type: ignore

            combined_log = (
                (report.run_log or "")
                + "\n"
                + (report.install_log or "")
                + "\n"
                + "\n".join(report.errors or [])
            )

            contract = None
            if analyze_logs is not None:
                contract = analyze_logs(
                    run_log=report.run_log or "",
                    install_log=report.install_log or "",
                    phase=report.phase or "",
                    extra_errors=list(report.errors or []),
                )
                # Enrich heal packages via AST on failing file
                source_mods = _resolve_missing_via_source(root, combined_log)
                for sm in source_mods:
                    pkg = _module_to_package(sm)
                    if pkg and pkg not in contract.heal_packages:
                        contract.heal_packages.append(pkg)
                        contract.healable = True

            # Attach diagnosis for hosting / user visibility
            report.details = dict(report.details or {})
            if contract is not None and contract.primary:
                report.details["error_contract"] = {
                    "category": contract.primary.category,
                    "action": contract.primary.suggested_action,
                    "location": contract.primary.location,
                    "package": contract.primary.suggested_package,
                    "healable": contract.healable,
                    "heal_packages": list(contract.heal_packages),
                    "summary_ar": contract.primary.summary_ar,
                    "confidence": contract.primary.confidence,
                }

            packages: list[str] = []
            if contract is not None:
                action = (
                    (contract.primary.suggested_action if contract.primary else "none")
                    or "none"
                )
                if contract.healable and contract.heal_packages and action in (
                    "install_package",
                    "fix_requirements",
                    "none",
                ):
                    packages = list(contract.heal_packages)
                    try:
                        from telegram_bot_engine.services.prod_hard_locks import auto_heal_pip_allowed
                        if not auto_heal_pip_allowed():
                            packages = []
                    except Exception:
                        packages = []
                elif (
                    action == "install_package"
                    and contract.primary
                    and contract.primary.suggested_package
                ):
                    packages = [contract.primary.suggested_package]
                elif action not in ("install_package", "fix_requirements", "none", ""):
                    # Smart self-heal for token/webhook/syntax before giving up
                    auto_notes = _smart_auto_heal(root, bot_token, combined_log, action)
                    heal_notes.extend(auto_notes)
                    report.warnings = list(report.warnings or []) + [
                        f"error_intel_action:{action}",
                        f"category:{(contract.primary.category if contract.primary else 'unknown')}",
                    ] + [f"auto_heal:{n}" for n in auto_notes[:6]]
                    # If token is fundamentally invalid, stop (user must provide new token)
                    if any(n.startswith("token_still_invalid:") for n in auto_notes):
                        report.install_log = all_install_log[-4000:]
                        report.message = (
                            "التوكن مرفوض من تليجرام. أرسل توكن جديد من @BotFather لهذا البوت."
                        )
                        return report
                    # If we applied a safe fix, retry the run in the next heal round
                    if auto_notes and heal_round < max_heal_rounds:
                        heal_notes.append(f"retry_after_auto_heal:{action}")
                        # Tell next report path what we fixed (user-facing on success)
                        if any("token_revalidated_ok" in n for n in auto_notes):
                            heal_notes.append("user_hint:تم حقن التوكن وتصحيح الإعدادات القديمة — إعادة التشغيل")
                        if any(n.startswith("delete_webhook:ok") or n.startswith("delete_webhook_after_token:ok") for n in auto_notes):
                            heal_notes.append("user_hint:تم إلغاء الـ webhook المتعارض")
                        if any(n.startswith("syntax_repair:") for n in auto_notes):
                            heal_notes.append("user_hint:تم إصلاح أخطاء صياغة تلقائياً")
                        continue
                    report.install_log = all_install_log[-4000:]
                    loc = contract.primary.location if contract.primary else ""
                    if loc and report.message:
                        report.message = f"{report.message} | الموقع: `{loc}`"
                    return report

            if not packages:
                missing_mods = _extract_missing_modules(combined_log)
                source_mods = _resolve_missing_via_source(root, combined_log)
                for sm in source_mods:
                    if sm not in missing_mods:
                        missing_mods.append(sm)
                for mod in missing_mods:
                    pkg = _module_to_package(mod)
                    if pkg and pkg not in packages:
                        packages.append(pkg)
                    elif not pkg:
                        heal_notes.append(f"skipped:{mod}")

            if not packages:
                report.install_log = all_install_log[-4000:]
                loc = _error_location_summary(report.run_log or "")
                if loc and report.message:
                    report.message = f"{report.message} | الموقع: `{loc}`"
                report.warnings = list(report.warnings or []) + ["not_healable_by_error_intel"]
                return report

            if heal_round >= max_heal_rounds:
                report.install_log = all_install_log[-4000:]
                report.warnings = list(report.warnings or []) + [
                    f"heal_exhausted after {max_heal_rounds} rounds; packages: {packages}"
                ]
                loc = _error_location_summary(report.run_log or "")
                if loc:
                    report.message = f"{report.message} | الموقع: `{loc}`"
                return report

            added = _ensure_packages_in_requirements(root, packages)
            if added:
                for a in added:
                    heal_notes.append(a)
            else:
                heal_notes.append(f"reinstall_try:{','.join(packages)}")

            try:
                py_h, mode_h, isolation_h, _note_h = _ensure_runtime(root)
                ok_direct, direct_log = _pip_install_packages_direct(  # gated inside by TBE_AUTO_HEAL_PIP
                        
                    py_h, packages, root, mode_h, isolation_h
                )
                all_install_log = (
                    all_install_log + "\n--- error_intel direct pip ---\n" + direct_log
                ).strip()
                if ok_direct:
                    heal_notes.append(f"direct_pip:{','.join(packages)}")
                else:
                    heal_notes.append(f"direct_pip_failed:{','.join(packages)}")
            except Exception as e:
                heal_notes.append(f"direct_pip_error:{type(e).__name__}")

            # continue loop → reinstall + rerun

        # fallback (should not reach)
        if last_report is None:
            return LiveRunReport(ok=False, phase="run", message="heal loop failed unexpectedly")
        last_report.install_log = all_install_log[-4000:]
        return last_report

    def _attempt_install_and_run(
        self,
        *,
        root: Path,
        entry: Path,
        bot_token: str,
        username: str,
        bot_id: int | None,
        run_seconds: float,
        install: bool,
        repair_notes: list[str],
        t0: float,
        heal_notes: list[str],
    ) -> LiveRunReport:
        install_log = ""
        mode = "unknown"
        isolation = root
        py = sys.executable
        note = ""

        try:
            py, mode, isolation, note = _ensure_runtime(root)
            if install:
                req = _find_requirements(root)
                ok_i, install_log, warns = _pip_install(py, req, root, mode, isolation)
                if not ok_i:
                    # automatic fallback: if venv failed install, retry with target once
                    if mode.startswith("venv"):
                        py2, mode2, isolation2 = sys.executable, "target-fallback", _deps_dir(root)
                        ok_i2, install_log2, warns2 = _pip_install(py2, req, root, mode2, isolation2)
                        install_log = install_log + "\n--- fallback target ---\n" + install_log2
                        warns = warns + warns2
                        if ok_i2:
                            py, mode, isolation = py2, mode2, isolation2
                            ok_i = True
                        else:
                            errs = _extract_pip_errors(install_log)
                            return LiveRunReport(
                                ok=False, phase="install", message="فشل تثبيت التبعيات",
                                bot_username=username, bot_id=bot_id,
                                install_log=install_log[-6000:],
                                errors=errs,
                                warnings=warns[:5],
                                entry_point=str(entry.relative_to(root)),
                                venv_path=str(isolation),
                                duration_ms=(time.perf_counter() - t0) * 1000,
                                details={"install_mode": mode, "note": note, "heal_notes": heal_notes},
                            )
                    else:
                        errs = _extract_pip_errors(install_log)
                        return LiveRunReport(
                            ok=False, phase="install", message="فشل تثبيت التبعيات",
                            bot_username=username, bot_id=bot_id,
                            install_log=install_log[-6000:],
                            errors=errs,
                            warnings=warns[:5],
                            entry_point=str(entry.relative_to(root)),
                            venv_path=str(isolation),
                            duration_ms=(time.perf_counter() - t0) * 1000,
                            details={"install_mode": mode, "note": note, "heal_notes": heal_notes},
                        )
        except subprocess.TimeoutExpired:
            return LiveRunReport(
                ok=False, phase="install", message="انتهت مهلة تثبيت التبعيات",
                bot_username=username, bot_id=bot_id, errors=["install_timeout"],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )
        except Exception as e:
            return LiveRunReport(
                ok=False, phase="install", message=f"install error: {type(e).__name__}: {e}",
                bot_username=username, bot_id=bot_id, errors=[str(e)],
                duration_ms=(time.perf_counter() - t0) * 1000,
            )

        from ..source_fix import discover_token_env_names

        from telegram_bot_engine.services.user_sandbox import clean_child_env
        env = clean_child_env(bot_token if "bot_token" in locals() else "")
        env["PYTHONUNBUFFERED"] = "1"
        token_envs = discover_token_env_names(root)
        for key in token_envs:
            env[key] = bot_token
        for key in ("TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TOKEN", "TG_TOKEN", "API_TOKEN", "TELEGRAM_TOKEN", "BOTTOKEN"):
            env[key] = bot_token

        # Token stays in process env only. Disk: sealed file, never plaintext .env.
        try:
            from telegram_bot_engine.services.user_sandbox.service import write_token_file
            write_token_file(root, bot_token)
        except Exception as _tok_exc:
            __import__("logging").getLogger("live_runner").warning(
                "sealed token write failed: %s", type(_tok_exc).__name__
            )
        try:
            env_path = root / ".env"
            kept: list[str] = []
            if env_path.exists():
                for ln in env_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                    key = ln.split("=", 1)[0].strip() if "=" in ln else ""
                    if key in {
                        "TELEGRAM_BOT_TOKEN", "BOT_TOKEN", "TOKEN", "TG_TOKEN",
                        "API_TOKEN", "TELEGRAM_TOKEN", "BOTTOKEN",
                        *set(token_envs),
                    }:
                        continue
                    kept.append(ln)
            kept.append("# TBE: token sealed in .tbe_bot_token — not written plaintext")
            env_path.write_text(chr(10).join(kept).strip() + chr(10), encoding="utf-8")
        except Exception as _env_exc:
            __import__("logging").getLogger("live_runner").warning(
                "could not update project .env markers: %s", _env_exc
            )
        if mode.startswith("target"):
            pp = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(isolation) + (os.pathsep + pp if pp else "")

        run_log = ""
        pid = None
        # Probe quickly for startup errors, then keep process alive in background.
        probe_seconds = float(os.environ.get("LIVE_RUN_PROBE_SECONDS", "25"))
        probe_seconds = max(8.0, min(probe_seconds, float(run_seconds)))
        try:
            proc = subprocess.Popen(
                [py, str(entry)],
                cwd=str(root),
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            pid = proc.pid
            # Wait probe window for early crash / auth errors
            try:
                out, _ = proc.communicate(timeout=probe_seconds)
                run_log = out or ""
            except subprocess.TimeoutExpired:
                # Still running after probe → success path: detach for remaining lifetime
                remaining = max(5.0, float(run_seconds) - probe_seconds)

                def _background_keep(p=proc, life=remaining):
                    try:
                        p.communicate(timeout=life)
                    except subprocess.TimeoutExpired:
                        try:
                            p.kill()
                            p.communicate(timeout=5)
                        except Exception:
                            pass
                    except Exception:
                        try:
                            p.kill()
                        except Exception:
                            pass

                threading.Thread(target=_background_keep, daemon=True).start()
                mins = max(1, int(round(float(run_seconds) / 60.0)))
                return LiveRunReport(
                    ok=True,
                    phase="run",
                    message=(
                        f"✅ البوت شغال الآن (~{mins} دقيقة). "
                        f"جرّبه على تيليجرام @{username or 'bot'} — "
                        f"عملية الخلفية pid={pid}."
                    ),
                    bot_username=username,
                    bot_id=bot_id,
                    install_log=install_log[-2000:],
                    run_log="(running in background — probe window clean)",
                    warnings=["running_in_background", f"lifetime_seconds:{int(run_seconds)}"],
                    pid=pid,
                    entry_point=str(entry.relative_to(root)),
                    venv_path=str(isolation),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    details={
                        "install_mode": mode,
                        "probe_seconds": probe_seconds,
                        "lifetime_seconds": run_seconds,
                        "background": True,
                        "heal_notes": heal_notes,
                    },
                )

            # Process ended during probe
            errors = _extract_errors(run_log)
            if proc.returncode == 0 and not errors:
                return LiveRunReport(
                    ok=True, phase="run",
                    message="انتهى بكود 0 (سكربت قصير أو إقلاع ناجح).",
                    bot_username=username, bot_id=bot_id,
                    install_log=install_log[-2000:], run_log=run_log[-3000:],
                    pid=pid, entry_point=str(entry.relative_to(root)),
                    venv_path=str(isolation),
                    duration_ms=(time.perf_counter() - t0) * 1000,
                    details={"install_mode": mode, "heal_notes": heal_notes},
                )
            if not errors:
                errors = [f"process exited with code {proc.returncode}"]
            return LiveRunReport(
                ok=False, phase="run",
                message=f"توقف مبكراً (code={proc.returncode})",
                bot_username=username, bot_id=bot_id,
                install_log=install_log[-2000:], run_log=run_log[-4000:],
                errors=errors, pid=pid, entry_point=str(entry.relative_to(root)),
                venv_path=str(isolation),
                duration_ms=(time.perf_counter() - t0) * 1000,
                details={"install_mode": mode, "heal_notes": heal_notes},
            )
        except Exception as e:
            return LiveRunReport(
                ok=False, phase="run", message=f"فشل التشغيل: {type(e).__name__}: {e}",
                bot_username=username, bot_id=bot_id,
                install_log=install_log[-2000:], run_log=run_log[-2000:],
                errors=[str(e)], entry_point=str(entry.relative_to(root)),
                duration_ms=(time.perf_counter() - t0) * 1000,
                details={"heal_notes": heal_notes},
            )




def run_bot_project(
    project_path: str | Path,
    bot_token: str,
    entry_hint: str | None = None,
    run_seconds: float = float(__import__('os').environ.get('LIVE_RUN_SECONDS', 900)),
) -> LiveRunReport:
    """Run a generated bot under isolation (Docker-first, fail-closed).

    Production / multi-tenant: Docker only. Local host process is refused unless
    isolation_policy explicitly allows it (dev + TBE_ALLOW_LOCAL_PROCESS=1).
    """
    import re as _re
    _raw_path = str(project_path or "")
    if _re.search(r"[;|&$`<>\\\n\r\0]", _raw_path):
        return LiveRunReport(
            ok=False,
            phase="security",
            message="invalid_path_characters",
            install_log="",
            run_log="",
            warnings=["path_rejected"],
            entry_point=entry_hint or "",
            duration_ms=0.0,
            details={"error": "invalid_path_characters"},
        )

    import os as _os
    # Single source of truth: isolation_policy (fail-closed multi-tenant/prod).
    try:
        from telegram_bot_engine.services.isolation_policy import decide_isolation
        _d = decide_isolation()
        require_docker = bool(_d.require_docker)
        allow_local = bool(_d.allow_local)
    except Exception:
        require_docker, allow_local = True, False
    prefer = (_os.environ.get("TBE_PREFER_DOCKER") or "1").strip().lower() not in {
        "0", "false", "no", "off",
    }
    if require_docker:
        prefer = True
        allow_local = False

    docker_err = ""
    if prefer or require_docker:
        try:
            from telegram_bot_engine.engines.generators.live_deployment.docker_process_driver import (
                DockerProcessDriver,
                docker_available,
            )
            if not docker_available():
                docker_err = "docker_daemon_unavailable"
            else:
                driver = DockerProcessDriver()
                st = driver.deploy(
                    str(project_path),
                    env_vars={"BOT_TOKEN": bot_token, "TELEGRAM_BOT_TOKEN": bot_token},
                    service_name="live-run",
                )
                if getattr(st, "status", "") == "running":
                    dep_id = st.deployment_id
                    lifetime = max(30.0, float(run_seconds))

                    def _auto_stop():
                        try:
                            time.sleep(lifetime)
                            driver.stop(dep_id)
                        except Exception:
                            pass

                    threading.Thread(target=_auto_stop, daemon=True).start()
                    mins = max(1, int(round(lifetime / 60.0)))
                    logs = driver.logs(dep_id, limit=20)
                    return LiveRunReport(
                        ok=True,
                        phase="run",
                        message=(
                            f"✅ البوت شغال داخل حاوية Docker معزولة (~{mins} دقيقة)"
                        ),
                        install_log="(docker image + pip inside container)",
                        run_log="\n".join(logs[-15:]) if logs else "(container started)",
                        warnings=["docker_isolated", f"lifetime_seconds:{int(lifetime)}"],
                        entry_point=entry_hint or "",
                        duration_ms=0.0,
                        details={
                            "provider": "docker",
                            "deployment_id": dep_id,
                            "service_id": getattr(st, "service_id", ""),
                        },
                    )
                docker_err = getattr(st, "message", "") or "docker_deploy_failed"
                __import__("logging").getLogger("live_runner").warning(
                    "Docker deploy failed: %s", str(docker_err)[:200]
                )
        except Exception as docker_exc:
            docker_err = str(docker_exc)
            __import__("logging").getLogger("live_runner").warning(
                "Docker path error: %s", docker_exc
            )

    if require_docker and not allow_local:
        return LiveRunReport(
            ok=False,
            phase="security",
            message=(
                "Docker مطلوب لتشغيل آمن وغير متاح أو فشل. "
                "لا يُسمح بالتشغيل المحلي في وضع الإنتاج "
                f"({docker_err or 'docker_required'})"
            ),
            install_log="",
            run_log="",
            warnings=["docker_required", "local_fallback_blocked"],
            entry_point=entry_hint or "",
            duration_ms=0.0,
            details={"provider": "none", "error": docker_err or "docker_required"},
        )

    # PRODUCTION RULE: no host-process fallback. Docker or reject.
    return LiveRunReport(
        ok=False,
        phase="security",
        message=(
            "التشغيل المحلي محذوف. التنفيذ فقط داخل حاوية معزولة (Docker). "
            f"({docker_err or 'docker_required'})"
        ),
        install_log="",
        run_log="",
        warnings=["host_process_removed", "docker_required"],
        entry_point=entry_hint or "",
        duration_ms=0.0,
        details={"provider": "none", "error": docker_err or "docker_required"},
    )

