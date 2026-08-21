"""Execute tools on the server. Groq never runs these — only requests them."""
from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    ok: bool
    tool: str
    message: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    needs_auth: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _output_dir() -> Path:
    try:
        from b2b_platform.paths import default_output_dir

        return Path(default_output_dir())
    except Exception:
        root = Path(os.getenv("OUTPUT_DIR") or (Path.home() / ".capability_maestro"))
        root.mkdir(parents=True, exist_ok=True)
        return root


def execute_tool(
    name: str,
    params: dict[str, Any] | None = None,
    *,
    user_id: int = 0,
    user_data: dict[str, Any] | None = None,
) -> ToolResult:
    """Dispatch a tool by name. Unknown tools fail closed."""
    params = dict(params or {})
    name = (name or "").strip()
    if not name:
        return ToolResult(ok=False, tool="", message="اسم الأداة فارغ")

    try:
        if name == "clone_repo":
            return _tool_clone_repo(params, user_id=user_id)
        if name == "create_repo":
            return _tool_create_repo(params, user_id=user_id)
        if name == "git_push":
            return _tool_git_push(params, user_id=user_id, user_data=user_data)
        if name == "git_pull":
            return _tool_git_pull(params, user_id=user_id, user_data=user_data)
        if name == "repo_inspect":
            return _tool_repo_inspect(params, user_data=user_data or {})
        if name == "repo_understand":
            return _tool_repo_understand(params, user_data=user_data or {})
        if name == "repo_modify":
            return _tool_repo_modify(params, user_data=user_data or {})
        if name in {"generate_bot", "refine_bot", "host_start", "host_stop", "host_status"}:
            # Handled by message_router generation/hosting paths — signal only
            return ToolResult(
                ok=True,
                tool=name,
                message=f"tool:{name}:defer_to_router",
                data={"defer": True, "params": params},
            )
        return ToolResult(ok=False, tool=name, message=f"أداة غير معروفة: {name}")
    except Exception as exc:
        logger.exception("tool %s failed", name)
        return ToolResult(ok=False, tool=name, message=f"{type(exc).__name__}: {exc}")


def _load_smart_clone():
    """Load smart_clone without circular engines package import (safe for @dataclass)."""
    from telegram_bot_engine.services.git_safe_import import get_smart_clone
    return get_smart_clone()


def _tool_clone_repo(params: dict[str, Any], *, user_id: int) -> ToolResult:
    _sc = _load_smart_clone()
    extract_repo_url = _sc.extract_repo_url
    smart_clone = _sc.smart_clone

    text = str(params.get("text") or params.get("url") or "")
    url = str(params.get("url") or "").strip() or (extract_repo_url(text) or "")
    token = str(params.get("token") or "").strip() or None
    branch = str(params.get("branch") or "").strip() or None
    try:
        depth = int(params.get("depth") if params.get("depth") is not None else 1)
    except (TypeError, ValueError):
        depth = 1

    if not url and not text:
        return ToolResult(ok=False, tool="clone_repo", message="مطلوب رابط مستودع")

    dest: Path
    try:
        from telegram_bot_engine.services.user_sandbox import get_user_sandbox

        dest = get_user_sandbox(int(user_id), _output_dir()).new_clone_dir(label="clone")
    except Exception:
        dest = _output_dir() / "clones" / str(user_id or "anon")
        dest.mkdir(parents=True, exist_ok=True)

    # Prefer strengthened smart_clone signature
    try:
        result = smart_clone(
            text or url,
            dest_dir=dest,
            token=token,
            depth=depth if depth > 0 else 1,
            url_override=url or None,
            branch=branch,
        )
    except TypeError:
        # older signature without branch
        result = smart_clone(
            text or url,
            dest_dir=dest,
            token=token,
            depth=depth if depth > 0 else 1,
            url_override=url or None,
        )

    if not result.ok:
        return ToolResult(
            ok=False,
            tool="clone_repo",
            message=result.message or "فشل السحب",
            data={
                "url": result.url,
                "stderr": (result.stderr or "")[:400],
                "strategy": getattr(result, "strategy", ""),
                "attempts": getattr(result, "attempts", 0),
            },
            needs_auth=bool(result.needs_auth),
        )
    return ToolResult(
        ok=True,
        tool="clone_repo",
        message=result.message or "تم السحب",
        data={
            "path": result.path,
            "url": result.url,
            "strategy": getattr(result, "strategy", ""),
            "attempts": getattr(result, "attempts", 0),
            "file_count": getattr(result, "file_count", 0),
            "meta": getattr(result, "meta", {}) or {},
        },
    )


def _tool_repo_inspect(
    params: dict[str, Any],
    *,
    user_data: dict[str, Any],
) -> ToolResult:
    from telegram_bot_engine.services.bot_inspector import inspect_bot_project
    from telegram_bot_engine.services.bot_inspector.service import resolve_user_bot_path

    path = str(params.get("path") or "").strip()
    if not path:
        path = resolve_user_bot_path(user_data=user_data)
    if not path:
        # active_repo from continuity
        active = user_data.get("active_repo")
        if isinstance(active, dict):
            path = str(active.get("path") or "")
    if not path or not Path(path).is_dir():
        return ToolResult(ok=False, tool="repo_inspect", message="لا يوجد مشروع/مستودع نشط للفحص")
    insp = inspect_bot_project(path)
    return ToolResult(
        ok=True,
        tool="repo_inspect",
        message=insp.chat_brief(),
        data=insp.to_dict(),
    )



def _tool_repo_understand(
    params: dict[str, Any],
    *,
    user_data: dict[str, Any],
) -> ToolResult:
    """Deep structural understanding via engine scanner — never the chat LLM."""
    path = str(params.get("path") or "").strip()
    url = str(params.get("url") or "").strip()
    if not path:
        active = user_data.get("active_repo")
        if isinstance(active, dict):
            path = str(active.get("path") or "")
            if not url:
                url = str(active.get("url") or "")
        if not path:
            path = str(user_data.get("last_project_path") or "")

    # If only URL given (or text contains github) and no local path → clone first
    text_blob = str(params.get("text") or params.get("raw_text") or "").strip()
    if (not path or not Path(path).is_dir()) and (url or text_blob):
        try:
            from telegram_bot_engine.services.git_safe_import import get_smart_clone
            sc = get_smart_clone()
            extract_repo_url = sc.extract_repo_url
            smart_clone = sc.smart_clone
            found = url or (extract_repo_url(text_blob) or "")
            if found:
                uid = int(user_data.get("user_id") or 0)
                try:
                    from telegram_bot_engine.services.user_sandbox import get_user_sandbox
                    dest = get_user_sandbox(uid, _output_dir()).new_clone_dir(label="understand")
                except Exception:
                    dest = _output_dir() / "clones" / str(uid or "anon")
                    dest.mkdir(parents=True, exist_ok=True)
                token = str(params.get("token") or "").strip() or None
                clone_res = smart_clone(found, dest_dir=dest, token=token, url_override=found)
                if not getattr(clone_res, "ok", False):
                    return ToolResult(
                        ok=False,
                        tool="repo_understand",
                        message=getattr(clone_res, "message", None) or "فشل سحب المستودع قبل الفهم",
                        data={"url": found},
                        needs_auth=bool(getattr(clone_res, "needs_auth", False)),
                    )
                path = str(clone_res.path or "")
                url = str(clone_res.url or found)
                user_data["active_repo"] = {"path": path, "url": url}
                user_data["last_project_path"] = path
        except Exception as exc:
            logger.exception("clone-before-understand failed")
            return ToolResult(
                ok=False,
                tool="repo_understand",
                message=f"تعذر السحب قبل الفهم: {type(exc).__name__}",
            )

    root = Path(path) if path else None
    if not root or not root.is_dir():
        return ToolResult(
            ok=False,
            tool="repo_understand",
            message="لا يوجد مستودع نشط. اسحب مستودعاً أولاً أو أرسل رابط GitHub مع «افهم المستودع».",
        )

    try:
        from telegram_bot_engine.services.repo_understanding import understand_repo
        from telegram_bot_engine.schemas.repo_contract import safe_contract_dict

        contract = understand_repo(root, remote_url=url or "")
        data = safe_contract_dict(contract)
        data["path"] = str(root)
        if url:
            data["url"] = url

        # Human-readable Arabic brief from real contract (not LLM invention)
        lines: list[str] = [
            "🔍 *فهم المستودع (محرك حتمي — ليس تخمين دردشة)*",
            f"• المسار: `{root}`",
        ]
        if url:
            lines.append(f"• الرابط: {url}")
        summary = str(data.get("summary") or getattr(contract, "summary", "") or "").strip()
        if summary:
            lines.append(f"• الملخص: {summary[:400]}")
        langs = data.get("languages") or []
        if langs:
            lines.append("• اللغات: " + ", ".join(str(x) for x in langs[:8]))
        fws = data.get("frameworks") or []
        if fws:
            lines.append("• الأُطر: " + ", ".join(str(x) for x in fws[:8]))
        style = str(data.get("architecture_style") or "").strip()
        if style:
            lines.append(f"• الأسلوب: {style}")
        # entry points
        eps = data.get("entry_points") or []
        ep_paths = []
        for e in eps[:8]:
            if isinstance(e, dict):
                ep_paths.append(str(e.get("path") or ""))
            else:
                ep_paths.append(str(getattr(e, "path", e)))
        ep_paths = [x for x in ep_paths if x]
        if ep_paths:
            lines.append("• نقاط الدخول: " + ", ".join(f"`{x}`" for x in ep_paths[:6]))
        # commands
        cmds = data.get("commands") or []
        cmd_names = []
        for c in cmds[:25]:
            if isinstance(c, dict):
                cmd_names.append(str(c.get("name") or ""))
            else:
                cmd_names.append(str(getattr(c, "name", c)))
        cmd_names = [c for c in cmd_names if c]
        if cmd_names:
            lines.append("• أوامر مكتشفة: " + ", ".join("/" + c.lstrip("/") for c in cmd_names[:15]))
        is_tg = bool(data.get("is_telegram_bot"))
        lines.append(f"• بوت تيليجرام؟ {'نعم' if is_tg else 'لا/غير مؤكد'}")
        fc = data.get("file_count") or data.get("python_file_count")
        if fc:
            lines.append(f"• ملفات: {fc}")
        conf = data.get("confidence")
        if conf is not None:
            try:
                lines.append(f"• ثقة التحليل: {float(conf):.0%}")
            except Exception:
                pass
        notes = data.get("notes") or []
        if notes:
            lines.append("• ملاحظات: " + "; ".join(str(n)[:80] for n in notes[:4]))

        brief = "\n".join(lines)
        # persist contract on active_repo for later tools
        active = user_data.get("active_repo")
        if not isinstance(active, dict):
            active = {}
        active.update({"path": str(root), "url": url or active.get("url") or "", "contract": data})
        user_data["active_repo"] = active
        user_data["last_project_path"] = str(root)

        return ToolResult(
            ok=True,
            tool="repo_understand",
            message=brief[:4000],
            data=data,
        )
    except Exception as exc:
        logger.exception("repo_understand failed")
        return ToolResult(
            ok=False,
            tool="repo_understand",
            message=f"فشل فهم المستودع: {type(exc).__name__}: {exc}",
            data={"path": str(root)},
        )


def _tool_repo_modify(
    params: dict[str, Any],
    *,
    user_data: dict[str, Any],
) -> ToolResult:
    """Prepare a refine request against the active repo/bot — engine does the work."""
    path = str(params.get("path") or "").strip()
    if not path:
        active = user_data.get("active_repo")
        if isinstance(active, dict):
            path = str(active.get("path") or "")
        if not path:
            path = str(user_data.get("last_project_path") or "")
    change = str(params.get("change") or params.get("spec_request") or params.get("text") or "").strip()
    if not path or not Path(path).is_dir():
        return ToolResult(ok=False, tool="repo_modify", message="لا يوجد مستودع/بوت نشط للتعديل")
    if not change:
        return ToolResult(
            ok=False,
            tool="repo_modify",
            message="صف التعديل المطلوب (مثال: أضف أمر /faq واحذف /cart)",
        )
    # Structural snapshot so router can merge into refine_bot
    try:
        from telegram_bot_engine.services.bot_inspector import inspect_bot_project
        insp = inspect_bot_project(path)
        snapshot = insp.to_dict()
        brief = insp.chat_brief()
    except Exception:
        snapshot = {"path": path}
        brief = f"المسار: {path}"
    return ToolResult(
        ok=True,
        tool="repo_modify",
        message=f"جاهز للتعديل عبر المحرك.\n{brief}\nالتغيير: {change[:500]}",
        data={
            "path": path,
            "change": change,
            "snapshot": snapshot,
            "defer_refine": True,
        },
    )
