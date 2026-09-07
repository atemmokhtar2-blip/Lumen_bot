"""Phase 2: bind a selected GitHub repo — official clone → active_repo.

Uses existing Power/smart_clone + user_sandbox + optional understand_repo.
No parallel clone stack.
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
    active_repo: dict[str, Any] = field(default_factory=dict)
    contract_summary: str = ""


def _resolve_url(user_id: int, resource_id: str, slots: dict[str, str] | None) -> tuple[str, str, str]:
    """Return (url, full_name, branch) from cache or slots."""
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
    # Fallback: scan numbered slots from last list render
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


def bind_github_repo(
    user_id: int,
    resource_id: str,
    *,
    slots: dict[str, str] | None = None,
    output_dir: str | Path | None = None,
    run_understand: bool = True,
) -> BindRepoResult:
    """Clone selected GitHub repo with stored PAT and build active_repo dict."""
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
            message_ar="اتصال GitHub غير متاح — أعد الربط بـ PAT.",
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
        result = sc.smart_clone(
            full_name or url,
            dest,
            token=token,
            url_override=url,
            branch=branch if branch and branch != "main" else None,
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
    active: dict[str, Any] = {
        "path": path,
        "url": final_url,
        "full_name": full_name,
        "source": "github_connection",
        "github_id": rid,
        "default_branch": branch,
    }

    summary = ""
    if run_understand and path:
        try:
            from lumen.engine.services.repo_understanding import understand_repo
            from lumen.engine.schemas.repo_contract import safe_contract_dict

            contract = understand_repo(path, remote_url=final_url)
            active["contract"] = safe_contract_dict(contract)
            parts = []
            if getattr(contract, "is_telegram_bot", False):
                parts.append("بوت تيليجرام")
            style = str(getattr(contract, "architecture_style", "") or "")
            if style:
                parts.append(style)
            frameworks = list(getattr(contract, "frameworks", None) or [])[:4]
            if frameworks:
                parts.append(", ".join(str(f) for f in frameworks))
            summary = " · ".join(parts) if parts else "تم فحص المستودع"
        except Exception:
            logger.exception("understand_repo after bind soft-fail uid=%s", uid)
            summary = "تم السحب — الفحص التفصيلي لاحقاً"

    try:
        from lumen.engine.services.user_sandbox import get_user_sandbox
        from lumen.bot.config import OUTPUT_DIR

        get_user_sandbox(uid, output_dir or OUTPUT_DIR).register_clone(
            path, url=final_url, label=Path(path).name if path else "repo"
        )
    except Exception:
        logger.exception("register_clone after bind failed uid=%s", uid)

    return BindRepoResult(
        ok=True,
        message_ar="تم سحب المستودع وربطه.",
        path=path,
        url=final_url,
        full_name=full_name,
        active_repo=active,
        contract_summary=summary,
    )
