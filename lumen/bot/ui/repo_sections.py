"""Paginated repo-understanding UI — short header + section buttons.

Avoids dumping multi-kilobyte blocks into a single Telegram message.
Sections live in user_data['repo_sections'] (plain) and optionally
user_data['repo_sections_rich'] (official Rich Message HTML).

Plain text is always available as fallback; Rich HTML uses Bot API 10.1+
tables / headings / lists / <details> via sendRichMessage.
"""
from __future__ import annotations

import html as html_lib
import logging
from typing import Any

from lumen.engine.services.ui_state.models import UiButton

from .keyboards import build_inline_keyboard
from .rtl_text import code_path, code_url

logger = logging.getLogger("lumen_bot.ui.repo_sections")

_MAX_SECTION = 3500
_MAX_RICH = 12000


def _clip(text: str, limit: int = _MAX_SECTION) -> str:
    from lumen.platform.textutil import clip_text
    return clip_text(text, limit, ellipsis="\n…(مختصر)")


def _esc(text: object) -> str:
    return html_lib.escape("" if text is None else str(text), quote=True)


def _attr(obj: Any, *names: str, default: str = "") -> str:
    if obj is None:
        return default
    if isinstance(obj, dict):
        for n in names:
            v = obj.get(n)
            if v is not None and str(v).strip():
                return str(v).strip()
        return default
    for n in names:
        v = getattr(obj, n, None)
        if v is not None and str(v).strip():
            return str(v).strip()
    return default


def _list_attr(obj: Any, name: str) -> list[Any]:
    if obj is None:
        return []
    if isinstance(obj, dict):
        raw = obj.get(name) or []
    else:
        raw = getattr(obj, name, None) or []
    return list(raw) if raw else []


def _format_entry_point(ep: Any) -> tuple[str, str, str]:
    """Return (path, reason, score) as clean strings — never object repr."""
    path = _attr(ep, "path", default=str(ep) if not hasattr(ep, "path") else "")
    # Guard against accidental full-repr leakage
    if path.startswith("EntryPoint(") or "reason=" in path:
        path = _attr(ep, "path", default="—")
    reason = _attr(ep, "reason", default="")
    score_raw = _attr(ep, "score", default="")
    try:
        score = f"{float(score_raw):.0f}" if score_raw not in ("", None) else ""
    except (TypeError, ValueError):
        score = str(score_raw)[:8] if score_raw else ""
    return path[:120], reason[:40], score


def _format_command(cmd: Any) -> tuple[str, str]:
    name = _attr(cmd, "name", default="")
    if name.startswith("DetectedCommand("):
        name = _attr(cmd, "name", default="—")
    if name and not name.startswith("/"):
        name = f"/{name}"
    src = _attr(cmd, "source_file", default="")
    return name[:40], src[:80]


def _format_handler(h: Any) -> tuple[str, str, str]:
    kind = _attr(h, "kind", default="")
    name = _attr(h, "name", default="")
    src = _attr(h, "source_file", default="")
    if kind.startswith("DetectedHandler("):
        kind, name, src = "—", "—", "—"
    return kind[:24], name[:40], src[:80]


def _human_summary_from_contract(repo_contract: Any) -> str:
    """Build a readable Arabic summary — never dump model/repr."""
    # Prefer explicit summary fields when they are real prose
    for field in ("summary", "architecture_summary"):
        val = _attr(repo_contract, field, default="")
        if val and not val.startswith(("RepoContract(", "root_path=", "EntryPoint(")):
            if len(val) > 40:
                return val[:2000]

    name = _attr(repo_contract, "repo_name", "name", default="")
    langs = _list_attr(repo_contract, "languages")
    fws = _list_attr(repo_contract, "frameworks")
    style = _attr(repo_contract, "architecture_style", default="")
    is_bot = bool(
        getattr(repo_contract, "is_telegram_bot", False)
        if not isinstance(repo_contract, dict)
        else repo_contract.get("is_telegram_bot")
    )
    files = 0
    try:
        files = int(
            getattr(repo_contract, "python_file_count", 0)
            or getattr(repo_contract, "file_count", 0)
            or (repo_contract.get("python_file_count") if isinstance(repo_contract, dict) else 0)
            or 0
        )
    except Exception:
        files = 0

    lines = []
    if name:
        lines.append(f"المستودع: {name}")
    if langs:
        lines.append("اللغات: " + ", ".join(str(x) for x in langs[:8]))
    if fws:
        lines.append("الأُطر: " + ", ".join(str(x) for x in fws[:10]))
    if style:
        lines.append(f"النمط المعماري: {style}")
    lines.append("بوت تيليجرام: " + ("نعم" if is_bot else "لا"))
    if files:
        lines.append(f"ملفات بايثون: {files}")

    entries = _list_attr(repo_contract, "entry_points")
    if entries:
        top = _format_entry_point(entries[0])[0]
        if top:
            lines.append(f"نقطة الدخول الرئيسية: {top}")

    cmds = _list_attr(repo_contract, "commands")
    if cmds:
        names = []
        for c in cmds[:8]:
            n, _ = _format_command(c)
            if n:
                names.append(n)
        if names:
            lines.append("أوامر: " + " · ".join(names))

    return "\n".join(lines) if lines else "تم فهم المستودع."


def build_summary_rich_html(repo_contract: Any, *, path: str = "", url: str = "") -> str:
    """Official Rich Message HTML for the summary section."""
    name = _attr(repo_contract, "repo_name", "name", default="مستودع")
    langs = [str(x) for x in _list_attr(repo_contract, "languages")[:8]]
    fws = [str(x) for x in _list_attr(repo_contract, "frameworks")[:12]]
    style = _attr(repo_contract, "architecture_style", default="—")
    is_bot = bool(
        getattr(repo_contract, "is_telegram_bot", False)
        if not isinstance(repo_contract, dict)
        else repo_contract.get("is_telegram_bot")
    )
    remote = _attr(repo_contract, "remote_url", default=url or "")
    conf = _attr(repo_contract, "confidence", default="")
    try:
        conf_s = f"{float(conf) * 100:.0f}%" if conf not in ("", None) else "—"
        if float(conf) > 1:
            conf_s = f"{float(conf):.0f}%"
    except (TypeError, ValueError):
        conf_s = "—"

    parts: list[str] = [f"<h3>📄 ملخص — {_esc(name)}</h3>"]

    overview_rows = [
        ["اللغات", ", ".join(langs) if langs else "—"],
        ["الأُطر", ", ".join(fws[:6]) if fws else "—"],
        ["النمط", style or "—"],
        ["بوت تيليجرام", "نعم" if is_bot else "لا"],
        ["الثقة", conf_s],
    ]
    if remote:
        overview_rows.append(["الرابط", remote[:80]])
    if path:
        overview_rows.append(["المسار", path[-60:] if len(path) > 60 else path])

    from lumen.bot.rich_messages import build_table_html

    parts.append(
        build_table_html(
            ["البند", "القيمة"],
            overview_rows,
            caption="نظرة عامة",
            bordered=True,
            striped=True,
            compact=True,
        )
    )

    # Entry points table
    entries = _list_attr(repo_contract, "entry_points")
    if entries:
        ep_rows = []
        for ep in entries[:10]:
            p, reason, score = _format_entry_point(ep)
            ep_rows.append([p or "—", reason or "—", score or "—"])
        parts.append("<h4>📂 نقاط الدخول</h4>")
        parts.append(
            build_table_html(
                ["المسار", "السبب", "الدرجة"],
                ep_rows,
                caption=f"{len(ep_rows)} نقطة",
                bordered=True,
                striped=True,
                compact=True,
            )
        )

    # Commands as list
    cmds = _list_attr(repo_contract, "commands")
    if cmds:
        items = []
        for c in cmds[:15]:
            n, src = _format_command(c)
            if n:
                items.append(f"<li><code>{_esc(n)}</code> — {_esc(src or '—')}</li>")
        if items:
            parts.append("<h4>⌨️ الأوامر</h4>")
            parts.append("<ul>" + "".join(items) + "</ul>")

    # Handlers in collapsible details
    handlers = _list_attr(repo_contract, "handlers")
    if handlers:
        h_items = []
        for h in handlers[:20]:
            kind, hname, src = _format_handler(h)
            h_items.append(
                f"<li><b>{_esc(kind)}</b> {_esc(hname)} <code>{_esc(src)}</code></li>"
            )
        if h_items:
            parts.append(
                "<details>"
                f"<summary>المُعالجات ({len(h_items)})</summary>"
                "<ul>" + "".join(h_items) + "</ul>"
                "</details>"
            )

    # Dependencies in collapsible details
    deps = [str(d) for d in _list_attr(repo_contract, "dependencies")[:30]]
    if deps or fws:
        dep_bits = []
        if fws:
            dep_bits.append("<p><b>أُطر:</b> " + _esc(", ".join(fws)) + "</p>")
        if deps:
            dep_bits.append(
                "<ul>" + "".join(f"<li><code>{_esc(d)}</code></li>" for d in deps) + "</ul>"
            )
        parts.append(
            "<details>"
            f"<summary>التبعيات ({len(deps)})</summary>"
            + "".join(dep_bits)
            + "</details>"
        )

    prose = _human_summary_from_contract(repo_contract)
    if prose and len(prose) > 20:
        # Only add free-text if it doesn't duplicate the table
        parts.append(f"<p>{_esc(prose[:800])}</p>")

    return "".join(parts)[:_MAX_RICH]


def build_entries_rich_html(repo_contract: Any) -> str:
    from lumen.bot.rich_messages import build_table_html

    entries = _list_attr(repo_contract, "entry_points")
    parts = ["<h3>📂 نقاط الدخول</h3>"]
    if not entries:
        parts.append("<p>لا نقاط دخول مكتشفة.</p>")
        return "".join(parts)
    rows = []
    for ep in entries[:15]:
        p, reason, score = _format_entry_point(ep)
        rows.append([p or "—", reason or "—", score or "—"])
    parts.append(
        build_table_html(
            ["المسار", "السبب", "الدرجة"],
            rows,
            caption=f"{len(rows)} نقطة",
            bordered=True,
            striped=True,
            compact=True,
        )
    )
    return "".join(parts)[:_MAX_RICH]


def build_deps_rich_html(repo_contract: Any) -> str:
    from lumen.bot.rich_messages import build_table_html

    fws = [str(x) for x in _list_attr(repo_contract, "frameworks")[:20]]
    deps = [str(d) for d in _list_attr(repo_contract, "dependencies")[:40]]
    parts = ["<h3>⚙️ التبعيات والأُطر</h3>"]
    if fws:
        parts.append(
            build_table_html(
                ["#", "الإطار"],
                [[str(i + 1), fw] for i, fw in enumerate(fws)],
                caption="أُطر العمل",
                bordered=True,
                striped=True,
                compact=True,
            )
        )
    if deps:
        parts.append(
            build_table_html(
                ["#", "الحزمة"],
                [[str(i + 1), d] for i, d in enumerate(deps[:25])],
                caption=f"{len(deps)} حزمة",
                bordered=True,
                striped=True,
                compact=True,
            )
        )
    if not fws and not deps:
        parts.append("<p>لا تبعيات مكتشفة.</p>")
    return "".join(parts)[:_MAX_RICH]


def build_header_rich_html(repo_contract: Any, *, path: str = "", url: str = "") -> str:
    from lumen.bot.rich_messages import build_table_html

    name = _attr(repo_contract, "repo_name", "name", default="مستودع")
    style = _attr(repo_contract, "architecture_style", default="—")
    is_bot = bool(
        getattr(repo_contract, "is_telegram_bot", False)
        if not isinstance(repo_contract, dict)
        else repo_contract.get("is_telegram_bot")
    )
    rows = [
        ["الاسم", name],
        ["النمط", style or "—"],
        ["بوت تيليجرام", "نعم" if is_bot else "لا"],
    ]
    if url:
        rows.append(["الرابط", url[:90]])
    if path:
        rows.append(["المسار", path[-70:] if len(path) > 70 else path])
    return (
        f"<h3>✅ تم فهم المستودع</h3>"
        + build_table_html(
            ["البند", "القيمة"],
            rows,
            caption="الرأس",
            bordered=True,
            striped=True,
            compact=True,
        )
    )[:_MAX_RICH]


def build_sections_from_contract(repo_contract: Any, *, path: str = "", url: str = "") -> dict[str, str]:
    """Split understand_repo output into named sections for pagination.

    Never stores object repr / dataclass dumps — only human-readable text.
    """
    sections: dict[str, str] = {}

    # ── Summary (human prose, never model dump) ──────────────────────
    try:
        if hasattr(repo_contract, "to_user_summary") and callable(
            getattr(repo_contract, "to_user_summary")
        ):
            raw = repo_contract.to_user_summary()
            summary = str(raw or "").strip()
            # Reject accidental dumps
            if summary.startswith(("RepoContract(", "root_path=", "EntryPoint(")):
                summary = _human_summary_from_contract(repo_contract)
        else:
            summary = _human_summary_from_contract(repo_contract)
        sections["summary"] = _clip(summary, 3200)
    except Exception:
        logger.exception("summary section build failed")
        sections["summary"] = "لا يتوفر ملخص."

    # ── Entry points ─────────────────────────────────────────────────
    try:
        entries = _list_attr(repo_contract, "entry_points")
        if entries:
            lines = ["📂 نقاط الدخول:"]
            for ep in entries[:12]:
                p, reason, score = _format_entry_point(ep)
                bit = f"• {code_path(p)}" if p else "• —"
                if reason:
                    bit += f" ({reason})"
                if score:
                    bit += f" [{score}]"
                lines.append(bit)
            sections["entries"] = "\n".join(lines)
        else:
            sections["entries"] = "لا نقاط دخول مكتشفة."
    except Exception:
        logger.exception("entries section build failed")
        sections["entries"] = "تعذّر استخراج نقاط الدخول."

    # ── Dependencies / frameworks ────────────────────────────────────
    try:
        deps = _list_attr(repo_contract, "dependencies")
        fws = _list_attr(repo_contract, "frameworks")
        lines = ["⚙️ التبعيات والأُطر:"]
        if fws:
            lines.append("أطر: " + ", ".join(str(x) for x in fws[:15]))
        if deps:
            lines.append("حزم:")
            for d in deps[:25]:
                lines.append(f"• `{d}`")
        if len(lines) == 1:
            lines.append("لا تبعيات مكتشفة.")
        sections["deps"] = _clip("\n".join(lines))
    except Exception:
        logger.exception("deps section build failed")
        sections["deps"] = "تعذّر استخراج التبعيات."

    # ── Meta header ──────────────────────────────────────────────────
    header_bits = ["✅ تم فهم المستودع"]
    if url:
        header_bits.append(f"• الرابط: {code_url(url)}")
    if path:
        header_bits.append(f"• المسار: {code_path(path)}")
    try:
        style = _attr(repo_contract, "architecture_style", default="")
        if style:
            header_bits.append(f"• النمط: `{style}`")
        is_bot = bool(
            getattr(repo_contract, "is_telegram_bot", False)
            if not isinstance(repo_contract, dict)
            else repo_contract.get("is_telegram_bot")
        )
        header_bits.append("• بوت تيليجرام: " + ("نعم" if is_bot else "لا"))
    except Exception:
        pass
    sections["header"] = "\n".join(header_bits)

    # ── Rich HTML (official Bot API 10.1+ Rich Messages) ─────────────
    try:
        rich: dict[str, str] = {
            "summary": build_summary_rich_html(repo_contract, path=path, url=url),
            "entries": build_entries_rich_html(repo_contract),
            "deps": build_deps_rich_html(repo_contract),
            "header": build_header_rich_html(repo_contract, path=path, url=url),
        }
        sections["_rich"] = rich  # type: ignore[assignment]
    except Exception:
        logger.exception("rich section build failed")

    return sections


def section_keyboard(*, user_id: int, show_run: bool = False) -> Any:
    rows = [
        (
            UiButton("📄 الملخص", "repo_sec", "summary", style="primary"),
            UiButton("📂 نقاط الدخول", "repo_sec", "entries", style="primary"),
        ),
        (
            UiButton("⚙️ التبعيات", "repo_sec", "deps", style="primary"),
            UiButton("↩️ الرأس", "repo_sec", "header"),
        ),
    ]
    if show_run:
        rows.append((UiButton("🚀 تشغيل / استضافة", "ask_bot_token", "run", style="success"),))
    rows.append((UiButton("🏠 الرئيسية", "home"),))
    return build_inline_keyboard(tuple(rows), user_id=int(user_id or 0))


def store_sections(user_data: dict, sections: dict[str, str]) -> None:
    if not isinstance(user_data, dict):
        return
    # Keep only small string values for plain sections
    clean = {
        str(k)[:24]: str(v)[:_MAX_SECTION]
        for k, v in (sections or {}).items()
        if k != "_rich" and isinstance(v, str)
    }
    user_data["repo_sections"] = clean
    # Store rich HTML separately (larger budget)
    rich = sections.get("_rich") if isinstance(sections, dict) else None
    if isinstance(rich, dict):
        user_data["repo_sections_rich"] = {
            str(k)[:24]: str(v)[:_MAX_RICH] for k, v in rich.items() if isinstance(v, str)
        }


def get_section(user_data: dict | None, key: str) -> str:
    if not isinstance(user_data, dict):
        return "لا بيانات."
    secs = user_data.get("repo_sections") or {}
    if not isinstance(secs, dict):
        return "لا بيانات."
    val = secs.get(key) or secs.get("header") or "القسم غير متاح."
    return str(val)[:_MAX_SECTION]


def get_section_rich(user_data: dict | None, key: str) -> str | None:
    """Return official Rich Message HTML for a section, or None."""
    if not isinstance(user_data, dict):
        return None
    rich = user_data.get("repo_sections_rich") or {}
    if not isinstance(rich, dict):
        return None
    val = rich.get(key)
    if not val or not isinstance(val, str):
        return None
    s = val.strip()
    return s if s else None
