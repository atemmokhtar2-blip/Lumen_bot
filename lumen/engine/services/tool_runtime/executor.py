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
        from lumen.platform.paths import default_output_dir

        return Path(default_output_dir())
    except Exception:
        root = Path(os.getenv("OUTPUT_DIR") or (Path.home() / ".lumen"))
        root.mkdir(parents=True, exist_ok=True)
        return root


def execute_tool(
    name: str,
    params: dict[str, Any] | None = None,
    *,
    user_id: int = 0,
    user_data: dict[str, Any] | None = None,
    confirmed: bool = False,
) -> ToolResult:
    """Dispatch a tool by name. Unknown tools fail closed.

    Mandatory path: ToolRequest → PolicyEngine → (ALLOW only) → provider.
    """
    params = dict(params or {})
    name = (name or "").strip()
    if not name:
        return ToolResult(ok=False, tool="", message="اسم الأداة فارغ")

    try:
        from lumen.engine.security.policy import PolicyEngine, ToolRequest
        confirmed_flag = bool(
            confirmed or (user_data or {}).get("confirmed") or params.pop("_confirmed", False)
        )
        decision = PolicyEngine().evaluate(
            ToolRequest(
                tool_name=name,
                params=params,
                user_id=str(user_id) if user_id else None,
                confirmed=confirmed_flag,
            )
        )
        if decision.needs_confirmation:
            return ToolResult(
                ok=False, tool=name,
                message=f"يتطلب تأكيد المستخدم: {decision.reason}",
                data={"needs_confirmation": True, "reason": decision.reason},
            )
        if not decision.allowed:
            return ToolResult(
                ok=False, tool=name,
                message=f"مرفوض بالسياسة: {decision.reason}",
                data={"denied": True, "reason": decision.reason},
            )
    except Exception as pol_exc:
        logger.warning("policy evaluation error (fail closed): %s", pol_exc)
        return ToolResult(ok=False, tool=name, message=f"policy_error: {type(pol_exc).__name__}")

    # Heavy-tool rate limit (clone / git / host) — per user, fail closed on abuse
    _HEAVY = {
        "clone_repo", "create_repo", "git_push", "git_pull",
        "repo_modify", "host_start", "generate_bot", "refine_bot",
    }
    if name in _HEAVY and int(user_id or 0) > 0:
        try:
            from lumen.platform.rate_limit import get_rate_limiter
            limit = int(os.getenv("TOOL_HEAVY_RPM") or "8")
            rl = get_rate_limiter()
            ok_rl = bool(rl.allow(f"tool:{int(user_id)}", limit=limit, window_sec=60.0))
            if not ok_rl:
                wait_s = 0
                try:
                    wait_s = int(rl.seconds_until_allow(f"tool:{int(user_id)}", limit=limit, window_sec=60.0))
                except Exception:
                    wait_s = 60
                return ToolResult(
                    ok=False,
                    tool=name,
                    message=f"rate_limited: حد الأدوات الثقيلة ({limit}/دقيقة). انتظر ~{wait_s}ث.",
                    data={"rate_limited": True, "wait_seconds": wait_s},
                )
        except Exception:
            logger.debug("tool rate limit probe failed — allowing (non-fatal)", exc_info=True)

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
    from lumen.engine.services.git_safe_import import get_smart_clone
    return get_smart_clone()


def _tool_clone_repo(params: dict[str, Any], *, user_id: int) -> ToolResult:
    import shutil

    if not shutil.which("git"):
        return ToolResult(
            ok=False,
            tool="clone_repo",
            message="git غير مثبت على السيرفر (binary not found in PATH)",
            data={"missing_binary": "git"},
        )
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
        from lumen.engine.services.user_sandbox import get_user_sandbox

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
    # Human message (never leak bare clone_ok)
    try:
        from lumen.engine.services.repo_understanding.repo_tools import run_tool
        st = run_tool("stats", Path(result.path)) if result.path else {}
    except Exception:
        st = {}
    msg = (
        f"تم سحب المستودع بنجاح.\n"
        f"• المسار: `{result.path}`\n"
        f"• الرابط: {result.url or ''}\n"
        f"• الملفات: {st.get('total_files') or getattr(result, 'file_count', 0)}\n"
        f"• إجمالي الأسطر: {st.get('total_lines', '—')}\n"
        f"• أسطر الكود: {st.get('code_lines', '—')}\n"
        f"• الاستراتيجية: {getattr(result, 'strategy', '') or '—'}"
    )
    return ToolResult(
        ok=True,
        tool="clone_repo",
        message=msg,
        data={
            "path": result.path,
            "url": result.url,
            "strategy": getattr(result, "strategy", ""),
            "attempts": getattr(result, "attempts", 0),
            "file_count": st.get("total_files") or getattr(result, "file_count", 0),
            "total_lines": st.get("total_lines"),
            "code_lines": st.get("code_lines"),
            "meta": getattr(result, "meta", {}) or {},
            "facts": st,
        },
    )



def _tool_repo_inspect(
    params: dict[str, Any],
    *,
    user_data: dict[str, Any],
) -> ToolResult:
    """Real measurements via repo_tools (not weak chat_brief only)."""
    path = str(params.get("path") or "").strip()
    if not path:
        active = user_data.get("active_repo")
        if isinstance(active, dict):
            path = str(active.get("path") or "")
        if not path:
            path = str(user_data.get("last_project_path") or "")
    if not path or not Path(path).is_dir():
        return ToolResult(ok=False, tool="repo_inspect", message="لا يوجد مشروع/مستودع نشط للفحص")

    from lumen.engine.services.repo_understanding.repo_tools import run_tool, run_core_toolkit
    root = Path(path)
    st = run_tool("stats", root)
    tree = run_tool("tree", root, max_entries=40)
    deps = run_tool("dependencies", root)
    eps = run_tool("entrypoints", root)
    tests = run_tool("test_discovery", root)
    lines = [
        "فحص المستودع (أدوات قياس):",
        f"• المسار: `{root}`",
        f"• الملفات: {st.get('total_files')}",
        f"• إجمالي الأسطر: {st.get('total_lines')}",
        f"• أسطر الكود: {st.get('code_lines')}",
        f"• حسب الامتداد: {st.get('files_by_extension')}",
        f"• نقاط الدخول: {[e.get('path') for e in (eps.get('entrypoints') or [])[:8]]}",
        f"• الحزم: {(deps.get('packages') or [])[:15]}",
        f"• ملفات اختبار: {tests.get('test_files')} / دوال: {tests.get('test_functions_total')}",
        f"• عينة مسارات: {(tree.get('paths') or [])[:20]}",
    ]
    return ToolResult(
        ok=True,
        tool="repo_inspect",
        message="\n".join(lines)[:4000],
        data={"stats": st, "entrypoints": eps, "dependencies": deps, "tests": tests},
    )


def _tool_repo_understand(
    params: dict[str, Any],
    *,
    user_data: dict[str, Any],
) -> ToolResult:
    """Engine pulls/gathers files; Grok (LLM) understands and explains to the user."""
    path = str(params.get("path") or "").strip()
    url = str(params.get("url") or "").strip()
    user_q = str(
        params.get("text") or params.get("raw_text") or params.get("question") or ""
    ).strip()
    if not path:
        active = user_data.get("active_repo")
        if isinstance(active, dict):
            path = str(active.get("path") or "")
            if not url:
                url = str(active.get("url") or "")
        if not path:
            path = str(user_data.get("last_project_path") or "")

    text_blob = user_q
    if (not path or not Path(path).is_dir()) and (url or text_blob):
        try:
            from lumen.engine.services.git_safe_import import get_smart_clone

            sc = get_smart_clone()
            found = url or (sc.extract_repo_url(text_blob) or "")
            if found:
                uid = int(user_data.get("user_id") or 0)
                try:
                    from lumen.engine.services.user_sandbox import get_user_sandbox

                    dest = get_user_sandbox(uid, _output_dir()).new_clone_dir(label="understand")
                except Exception:
                    dest = _output_dir() / "clones" / str(uid or "anon")
                    dest.mkdir(parents=True, exist_ok=True)
                token = str(params.get("token") or "").strip() or None
                clone_res = sc.smart_clone(found, dest_dir=dest, token=token, url_override=found)
                if not getattr(clone_res, "ok", False):
                    return ToolResult(
                        ok=False,
                        tool="repo_understand",
                        message=getattr(clone_res, "message", None)
                        or "clone failed before understand",
                        data={"url": found},
                        needs_auth=bool(getattr(clone_res, "needs_auth", False)),
                    )
                path = str(clone_res.path or "")
                url = str(clone_res.url or found)
                _prev = dict(user_data.get("active_repo") or {})
                _prev.update({"path": path, "url": url, "bound_for_grok": True})
                user_data["active_repo"] = _prev
                user_data["last_project_path"] = path
        except Exception as exc:
            logger.exception("clone-before-understand failed")
            return ToolResult(
                ok=False,
                tool="repo_understand",
                message=f"clone error: {type(exc).__name__}",
            )

    root = Path(path) if path else None
    if not root or not root.is_dir():
        return ToolResult(
            ok=False,
            tool="repo_understand",
            message="no active repo — clone first or send a Git URL with the request",
        )

    try:
        from lumen.engine.services.repo_understanding.llm_explain import (
            explain_repo_with_llm,
        )

        explanation, meta = explain_repo_with_llm(
            root,
            user_question=user_q or "understand this repository",
            url=url or "",
        )
        active = user_data.get("active_repo")
        if not isinstance(active, dict):
            active = {}
        dos = (meta or {}).get("dossier") or {}
        active.update(
            {
                "path": str(root),
                "url": url or active.get("url") or "",
                "dossier": dos,
                "facts": dos.get("facts") or active.get("facts") or {},
                "bound_for_grok": True,
            }
        )
        user_data["active_repo"] = active
        user_data["last_project_path"] = str(root)

        # User-facing text only — no English debug banners.
        return ToolResult(
            ok=True,
            tool="repo_understand",
            message=(explanation or "")[:4000],
            data={
                "path": str(root),
                "url": url,
                "meta": {k: v for k, v in (meta or {}).items() if k != "dossier"},
                "dossier": (meta or {}).get("dossier") or {},
            },
        )
    except Exception as exc:
        logger.exception("repo_understand/llm failed")
        return ToolResult(
            ok=False,
            tool="repo_understand",
            message=f"repo_understand failed: {type(exc).__name__}: {exc}",
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
        from lumen.engine.services.bot_inspector import inspect_bot_project
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
