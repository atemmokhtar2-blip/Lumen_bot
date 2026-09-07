"""Phase 2 — bind selected GitHub repo into Lumen's real active_repo plane.

Integrates with existing platform paths (not a parallel stack):
  smart_clone → register_clone → understand_repo → dossier → active_repo
  → pending_run (if telegram bot) → repo_sections payload for UI
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import token_store

logger = logging.getLogger("lumen.connections.bind_repo")


@dataclass
class BindRepoResult:
    ok: bool
    message_ar: str = ""
    path: str = ""
    url: str = ""
    full_name: str = ""
    needs_auth: bool = False
    is_runnable: bool = False
    entry_point: str = ""
    active_repo: dict[str, Any] = field(default_factory=dict)
    sections: dict[str, Any] = field(default_factory=dict)
    header_ar: str = ""
    contract_summary: str = ""
    agent_brief: str = ""


def _resolve_url(user_id: int, resource_id: str, slots: dict[str, str] | None) -> tuple[str, str, str]:
    slots = slots or {}
    item = token_store.resolve_cached_repo(int(user_id), str(resource_id))
    if item:
        full = str(item.get("full_name") or "").strip()
        url = str(item.get("html_url") or "").strip()
        branch = str(item.get("default_branch") or "main").strip() or "main"
        if not url and full:
            url = f"https://github.com/{full}"
        return url, full, branch
    full = str(slots.get("gh_selected_full") or "").strip()
    url = str(slots.get("gh_selected_url") or "").strip()
    branch = str(slots.get("gh_selected_branch") or "main").strip() or "main"
    if not url and full:
        url = f"https://github.com/{full}"
    if not url:
        rid = str(resource_id)
        for i in range(12):
            if str(slots.get(f"gh_r{i}_id") or "") == rid:
                full = str(slots.get(f"gh_r{i}_full") or full).strip()
                url = str(slots.get(f"gh_r{i}_url") or "").strip()
                if not url and full:
                    url = f"https://github.com/{full}"
                break
    return url, full, branch


def _is_runnable_contract(contract: Any) -> bool:
    try:
        from lumen.engine.services.repo_understanding.contract import is_runnable_bot

        return bool(is_runnable_bot(contract))
    except Exception:
        pass
    try:
        if getattr(contract, "is_telegram_bot", False):
            return True
        style = str(getattr(contract, "architecture_style", "") or "")
        if style in {"telegram_bot", "generation_engine"}:
            return True
        fws = ("python-telegram-bot", "aiogram", "pyTelegramBotAPI", "pyrogram", "telebot")
        frameworks = [str(f) for f in (getattr(contract, "frameworks", None) or [])]
        if any(any(x in f for x in fws) for f in frameworks):
            return True
    except Exception:
        pass
    return False


def bind_github_repo(
    user_id: int,
    resource_id: str,
    *,
    slots: dict[str, str] | None = None,
    output_dir: str | Path | None = None,
    run_understand: bool = True,
) -> BindRepoResult:
    """Clone selected repo with stored PAT and produce platform-shaped active_repo."""
    uid = int(user_id or 0)
    rid = str(resource_id or "").strip()
    if uid <= 0 or not rid:
        return BindRepoResult(ok=False, message_ar="اختيار غير صالح.")

    url, full_name, branch = _resolve_url(uid, rid, slots)
    if not url:
        return BindRepoResult(
            ok=False,
            message_ar="تعذر معرفة رابط المستودع — حدّث قائمة GitHub وأعد الاختيار.",
        )

    token = token_store.load_github_token(uid)
    if not token:
        return BindRepoResult(
            ok=False,
            needs_auth=True,
            message_ar="اتصال GitHub غير متاح — أعد الربط بـ PAT (صلاحية Contents: Read).",
            full_name=full_name,
            url=url,
        )

    try:
        from lumen.bot.config import OUTPUT_DIR
        from lumen.engine.services.user_sandbox import get_user_sandbox
        from lumen.engine.services.git_safe_import import get_smart_clone

        root = output_dir or OUTPUT_DIR
        dest = get_user_sandbox(uid, root).new_clone_dir(
            label=(full_name or "repo").replace("/", "_")[:40]
        )
        sc = get_smart_clone()
        # Prefer branch only when non-default; empty lets remote HEAD win
        br = branch if branch and branch not in {"main", "master"} else None
        result = sc.smart_clone(
            full_name or url,
            dest,
            token=token,
            url_override=url,
            branch=br,
            depth=1,
        )
    except Exception as exc:
        logger.exception("bind_github_repo clone failed uid=%s", uid)
        return BindRepoResult(
            ok=False,
            message_ar=f"فشل السحب: {type(exc).__name__}",
            full_name=full_name,
            url=url,
        )

    if not getattr(result, "ok", False):
        needs = bool(getattr(result, "needs_auth", False))
        msg = str(getattr(result, "message", "") or "فشل سحب المستودع")[:300]
        return BindRepoResult(
            ok=False,
            needs_auth=needs,
            message_ar=msg,
            full_name=full_name,
            url=url,
        )

    path = str(getattr(result, "path", "") or "")
    final_url = str(getattr(result, "url", "") or url)

    try:
        from lumen.bot.config import OUTPUT_DIR
        from lumen.engine.services.user_sandbox import get_user_sandbox

        get_user_sandbox(uid, output_dir or OUTPUT_DIR).register_clone(
            path, url=final_url, label=Path(path).name if path else "repo"
        )
    except Exception:
        logger.exception("register_clone after bind failed uid=%s", uid)

    active: dict[str, Any] = {
        "path": path,
        "url": final_url,
        "full_name": full_name,
        "source": "github_connection",
        "github_id": rid,
        "default_branch": branch,
        "bound_for_grok": True,
    }

    # Dossier (same as git_router post-clone)
    if path:
        try:
            from lumen.engine.services.repo_understanding.llm_explain import gather_repo_dossier

            dos = gather_repo_dossier(Path(path))
            active["dossier"] = {
                "root": dos.get("root"),
                "tree": dos.get("tree"),
                "facts": dos.get("facts"),
                "key_file_names": list((dos.get("key_files") or {}).keys()),
            }
            active["facts"] = dos.get("facts") or {}
        except Exception:
            logger.exception("dossier after bind soft-fail uid=%s", uid)

    contract = None
    summary = ""
    is_runnable = False
    entry = ""
    sections: dict[str, Any] = {}
    header = f"✅ تم سحب `{full_name or path}`"
    agent_brief = ""

    if run_understand and path:
        # --- Structural contract (scanner + intelligence) ---
        contract = None
        try:
            from lumen.engine.services.repo_understanding import understand_repo
            from lumen.engine.schemas.repo_contract import safe_contract_dict

            contract = understand_repo(path, remote_url=final_url)
            active["contract"] = safe_contract_dict(contract)
            is_runnable = _is_runnable_contract(contract)
            if getattr(contract, "entry_points", None):
                try:
                    entry = str(contract.entry_points[0].path or "")
                except Exception:
                    entry = ""
            parts: list[str] = []
            if getattr(contract, "is_telegram_bot", False):
                parts.append("بوت تيليجرام")
            style = str(getattr(contract, "architecture_style", "") or "")
            if style:
                parts.append(style)
            frameworks = list(getattr(contract, "frameworks", None) or [])[:4]
            if frameworks:
                parts.append(", ".join(str(f) for f in frameworks))
            summary = " · ".join(parts) if parts else "فحص هيكلي"
            try:
                from lumen.bot.ui.repo_sections import build_sections_from_contract

                sections = build_sections_from_contract(
                    contract, path=path or "", url=final_url or ""
                )
                header = sections.get("header") or header
            except Exception:
                logger.exception("build_sections_from_contract soft-fail")
        except Exception:
            logger.exception("understand_repo after bind soft-fail uid=%s", uid)
            summary = "تم السحب — الفحص الهيكلي لاحقاً"
            header = f"✅ تم سحب المستودع\n• {final_url}\n• {path}"

        # --- Agent-grade understanding (same plane as tool repo_understand) ---
        try:
            from lumen.engine.services.repo_understanding.llm_explain import (
                explain_repo_with_llm,
            )

            question = (
                "افهم المستودع بدقة عالية: الغرض، البنية، نقطة الدخول، "
                "الأطر، متغيرات البيئة المطلوبة، وكيف يُشغَّل. "
                "اذكر المخاطر والفجوات إن وُجدت."
            )
            explanation, meta = explain_repo_with_llm(
                Path(path),
                user_question=question,
                url=final_url or "",
                user_id=uid,
            )
            agent_brief = (explanation or "").strip()[:6000]
            dos = (meta or {}).get("dossier") or {}
            if dos:
                active["dossier"] = {
                    "root": dos.get("root") or active.get("dossier", {}).get("root"),
                    "tree": dos.get("tree") or active.get("dossier", {}).get("tree"),
                    "facts": dos.get("facts") or active.get("facts") or {},
                    "key_file_names": list(
                        (dos.get("key_files") or dos.get("key_file_names") or {}).keys()
                        if isinstance(dos.get("key_files"), dict)
                        else (dos.get("key_file_names") or [])
                    ),
                    "tools_run": dos.get("tools_run") or (meta or {}).get("tools_run"),
                }
                active["facts"] = dos.get("facts") or active.get("facts") or {}
            if agent_brief:
                active["agent_brief"] = agent_brief
                active["understanding_level"] = "agent"
                active["understood_at"] = __import__("time").time()
                active["bound_for_grok"] = True
                # Prefer agent summary in header when available
                if not sections:
                    header = f"✅ فهم الوكيل للمستودع `{full_name or path}`\n\n{agent_brief[:1500]}"
                else:
                    # Attach brief under structural header for UI
                    header = (sections.get("header") or header) + "\n\n🧠 " + agent_brief[:1200]
                    sections = dict(sections)
                    sections["agent_brief"] = agent_brief[:3500]
            else:
                active["understanding_level"] = "structural"
                active.setdefault("bound_for_grok", True)
        except Exception:
            logger.exception("explain_repo_with_llm after bind failed uid=%s", uid)
            active["understanding_level"] = active.get("understanding_level") or "structural"
            active.setdefault("bound_for_grok", True)

    return BindRepoResult(
        ok=True,
        message_ar="تم سحب المستودع وربطه وفهمه عبر محرك الوكيل.",
        path=path,
        url=final_url,
        full_name=full_name,
        is_runnable=is_runnable,
        entry_point=entry,
        active_repo=active,
        sections=sections if isinstance(sections, dict) else {},
        header_ar=header,
        contract_summary=summary,
        agent_brief=agent_brief,
    )


def apply_bind_to_user_data(
    user_data: dict[str, Any],
    bind: BindRepoResult,
    *,
    user: Any = None,
) -> None:
    """Write bind result into session-shaped user_data (platform keys)."""
    if not bind.ok or not bind.active_repo:
        return
    user_data["active_repo"] = dict(bind.active_repo)
    user_data["last_project_path"] = bind.path
    user_data["last_clone_url"] = bind.url
    if bind.sections:
        try:
            from lumen.bot.ui.repo_sections import store_sections

            store_sections(user_data, bind.sections)
        except Exception:
            logger.exception("store_sections after bind failed")
    if bind.is_runnable and bind.path:
        run_seconds = 1800
        try:
            from lumen.bot.helpers import plan_live_seconds

            if user is not None:
                run_seconds = int(plan_live_seconds(user))
        except Exception:
            try:
                import os

                run_seconds = int(os.environ.get("LIVE_RUN_SECONDS", "1800") or 1800)
            except Exception:
                run_seconds = 1800
        user_data["pending_run"] = {
            "project_path": bind.path,
            "entry_point": bind.entry_point or "",
            "run_seconds": run_seconds,
        }
