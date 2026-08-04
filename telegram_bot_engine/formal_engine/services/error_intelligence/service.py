"""
Error Intelligence Service — parse + classify + diagnose runtime/install logs.

No LLM. Rules + regex + traceback structure only.
Produces ErrorContract used by LiveRunner heal and future hosting health checks.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...schemas.error_contract import (
    DiagnosedError,
    ErrorContract,
    LogEvent,
    StackFrame,
    TracebackInfo,
)

# Reuse LiveRunner mapping when available (lazy to avoid cycles at import time)
def _module_to_package(module: str) -> str | None:
    try:
        from ..live_runner.service import _module_to_package as m2p
        return m2p(module)
    except Exception:
        return module if module and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,60}", module) else None


_TB_SPLIT = re.compile(r"(?=Traceback \(most recent call last\):)")
_FRAME_RE = re.compile(
    r'File "([^"]+)", line (\d+)(?:, in ([^\n]+))?\n(?:\s{2,4}([^\n]+))?',
)
_EXC_RE = re.compile(
    r"^([A-Za-z_][\w.]*(?:Error|Exception|Warning|Exit|Interrupt)?):\s*(.*)$",
    re.M,
)
_MOD_RE = re.compile(
    r"(?:ModuleNotFoundError|ImportError):\s*No module named ['\"]([^'\"]+)['\"]"
)
_IMPORT_HINT = re.compile(
    r"(?:from\s+([A-Za-z_][\w.]*)\s+import|import\s+([A-Za-z_][\w.]*))"
)

# Classification rules: (category, severity, title_ar, action, patterns)
_RULES: list[tuple[str, str, str, str, list[str]]] = [
    ("dependency", "high", "مكتبة ناقصة", "install_package",
     ["ModuleNotFoundError", "No module named", "ImportError: No module"]),
    ("syntax", "high", "خطأ في صياغة الكود", "fix_syntax",
     ["SyntaxError", "IndentationError", "TabError"]),
    ("config", "high", "إعداد / متغير بيئة", "set_env",
     ["KeyError: 'TELEGRAM", "KeyError: 'BOT_TOKEN", "Missing token", "BOT_TOKEN", "API key"]),
    ("telegram_api", "critical", "مشكلة Telegram API", "check_token",
     ["Unauthorized", "InvalidToken", "Conflict: terminated by other getUpdates",
      "TimedOut", "RetryAfter", "Bad Request", "chat not found"]),
    ("network", "medium", "مشكلة شبكة", "check_network",
     ["ConnectionError", "ConnectionRefusedError", "NameResolutionError",
      "Temporary failure in name resolution", "Max retries exceeded", "SSLError"]),
    ("permission", "high", "صلاحيات / ملفات", "escalate",
     ["PermissionError", "Read-only file system", "Operation not permitted"]),
    ("timeout", "medium", "انتهت المهلة", "retry",
     ["TimeoutExpired", "timed out", "TimeoutError", "install_timeout"]),
    ("conflict", "medium", "تعارض تبعيات", "fix_requirements",
     ["ResolutionImpossible", "Depends on", "conflict", "Could not find a version that satisfies"]),
    ("runtime", "medium", "خطأ تشغيل", "fix_code",
     ["AttributeError", "TypeError", "NameError", "ValueError", "KeyError",
      "IndexError", "RuntimeError", "AssertionError", "ZeroDivisionError"]),
]


def _parse_traceback_block(block: str) -> TracebackInfo | None:
    block = (block or "").strip()
    if "Traceback" not in block and "Error" not in block:
        return None
    frames: list[StackFrame] = []
    for m in _FRAME_RE.finditer(block):
        frames.append(StackFrame(
            file=m.group(1) or "",
            line=int(m.group(2) or 0),
            function=(m.group(3) or "").strip(),
            code=(m.group(4) or "").strip(),
        ))
    exc_type, exc_msg = "", ""
    # last non-empty line often ExceptionType: message
    for line in reversed(block.splitlines()):
        line = line.strip()
        if not line:
            continue
        em = re.match(
            r"^([A-Za-z_][\w.]*(?:Error|Exception|Warning)?):\s*(.*)$",
            line,
        )
        if em:
            exc_type, exc_msg = em.group(1), em.group(2)
            break
        if line.startswith("ModuleNotFoundError") or line.startswith("ImportError"):
            parts = line.split(":", 1)
            exc_type = parts[0].strip()
            exc_msg = parts[1].strip() if len(parts) > 1 else ""
            break
    if not frames and not exc_type:
        return None
    return TracebackInfo(
        exception_type=exc_type,
        exception_message=exc_msg,
        frames=frames,
        raw=block[-1500:],
    )


def _extract_tracebacks(log: str) -> list[TracebackInfo]:
    if not log:
        return []
    out: list[TracebackInfo] = []
    parts = _TB_SPLIT.split(log)
    for p in parts:
        tb = _parse_traceback_block(p)
        if tb:
            out.append(tb)
    # single-line errors without full traceback
    if not out:
        for line in log.splitlines():
            if any(k in line for k in ("Error", "Exception", "ModuleNotFound")):
                tb = _parse_traceback_block(line)
                if tb:
                    out.append(tb)
    return out


def _missing_module_from_tb(tb: TracebackInfo) -> str:
    text = f"{tb.exception_message}\n{tb.raw}"
    m = _MOD_RE.search(text) or re.search(
        r"No module named ['\"]([^'\"]+)['\"]", text
    )
    raw = m.group(1).strip() if m else ""
    # promote via import hints in code lines
    for fr in tb.frames:
        hm = _IMPORT_HINT.search(fr.code or "")
        if hm:
            full = (hm.group(1) or hm.group(2) or "").strip()
            if full and (not raw or full == raw or full.startswith(raw + ".")):
                return full
    return raw


def _classify_from_text(text: str) -> tuple[str, str, str, str]:
    """Return category, severity, title_ar, action."""
    for cat, sev, title, action, patterns in _RULES:
        for pat in patterns:
            if pat.lower() in text.lower() or pat in text:
                return cat, sev, title, action
    return "unknown", "medium", "خطأ غير مصنّف", "escalate"


def _diagnose_traceback(tb: TracebackInfo) -> DiagnosedError:
    text = f"{tb.exception_type}: {tb.exception_message}\n{tb.raw}"
    cat, sev, title, action = _classify_from_text(text)
    missing = ""
    suggested_pkg = ""
    if cat == "dependency" or "ModuleNotFound" in (tb.exception_type or ""):
        missing = _missing_module_from_tb(tb)
        if missing:
            suggested_pkg = _module_to_package(missing) or ""
            if suggested_pkg:
                action = "install_package"
            elif not suggested_pkg and missing:
                action = "install_package"
        cat = "dependency"
        sev = "high"
        title = "مكتبة ناقصة"

    summary = ""
    if cat == "dependency" and missing:
        summary = f"الموديول `{missing}` غير مثبت."
        if suggested_pkg:
            summary += f" الحزمة المقترحة: `{suggested_pkg}`."
    elif cat == "syntax":
        summary = f"خطأ صياغة عند `{tb.location}`."
    elif cat == "telegram_api":
        summary = "مشكلة في الاتصال بـ Telegram (توكن / تعارض getUpdates / حدود)."
    elif cat == "config":
        summary = "متغير بيئة أو إعداد ناقص (غالباً التوكن)."
    elif tb.exception_type:
        summary = f"`{tb.exception_type}`: {tb.exception_message[:160]}"

    conf = 0.9 if cat != "unknown" and (tb.location or missing) else 0.55
    if cat == "unknown":
        conf = 0.35

    return DiagnosedError(
        category=cat,  # type: ignore[arg-type]
        severity=sev,  # type: ignore[arg-type]
        title=title,
        summary_ar=summary,
        exception_type=tb.exception_type,
        exception_message=tb.exception_message[:400],
        location=tb.location,
        missing_module=missing,
        suggested_package=suggested_pkg or "",
        suggested_action=action,  # type: ignore[arg-type]
        confidence=conf,
        evidence=[tb.raw[:300]] if tb.raw else [],
        traceback=tb,
    )


def _scan_events(log: str, source: str) -> list[LogEvent]:
    events: list[LogEvent] = []
    if not log:
        return events
    for i, line in enumerate(log.splitlines(), 1):
        s = line.strip()
        if not s:
            continue
        level = "INFO"
        low = s.lower()
        if "error" in low or "traceback" in low or "exception" in low:
            level = "ERROR"
        elif "warning" in low or "warn" in low:
            level = "WARNING"
        elif "critical" in low or "fatal" in low:
            level = "CRITICAL"
        elif s.startswith("DEBUG") or "| DEBUG" in s:
            level = "DEBUG"
        if level in ("ERROR", "WARNING", "CRITICAL") or "Traceback" in s:
            events.append(LogEvent(level=level, message=s[:300], source=source, line_no=i))
    return events[:80]


def analyze_logs(
    *,
    run_log: str = "",
    install_log: str = "",
    phase: str = "",
    exit_code: int | None = None,
    extra_errors: list[str] | None = None,
) -> ErrorContract:
    """Main entry: turn raw logs into ErrorContract."""
    combined = "\n".join(
        x for x in (install_log, run_log, "\n".join(extra_errors or [])) if x
    )
    events = _scan_events(install_log, "install") + _scan_events(run_log, "run")
    tbs = _extract_tracebacks(combined)
    diagnosed: list[DiagnosedError] = []
    for tb in tbs:
        diagnosed.append(_diagnose_traceback(tb))

    # line-only / free-text errors (no full traceback)
    if not diagnosed:
        blobs = list(extra_errors or [])
        if run_log:
            blobs.append(run_log)
        if install_log:
            blobs.append(install_log)
        for e in blobs:
            if not e or not e.strip():
                continue
            cat, sev, title, action = _classify_from_text(e)
            if cat == "unknown" and "error" not in e.lower() and "exception" not in e.lower():
                continue
            # try extract exception type from first line
            first = e.strip().splitlines()[0][:240]
            em = re.match(
                r"^(?:[\w.]*)?([A-Za-z_][\w.]*(?:Error|Exception)):\s*(.*)$",
                first,
            )
            exc_t, exc_m = ("", first)
            if em:
                exc_t, exc_m = em.group(1), em.group(2)
            diagnosed.append(DiagnosedError(
                category=cat,  # type: ignore[arg-type]
                severity=sev,  # type: ignore[arg-type]
                title=title,
                summary_ar=(exc_m or e)[:200],
                exception_type=exc_t,
                exception_message=(exc_m or "")[:400],
                suggested_action=action,  # type: ignore[arg-type]
                confidence=0.7 if cat != "unknown" else 0.4,
                evidence=[e[:300]],
            ))
            break  # one primary free-text diagnosis is enough

    # dedupe by location+exception_type
    seen: set[str] = set()
    unique: list[DiagnosedError] = []
    for d in diagnosed:
        key = f"{d.category}|{d.location}|{d.exception_type}|{d.missing_module}"
        if key not in seen:
            seen.add(key)
            unique.append(d)

    primary = unique[0] if unique else None
    # severity order for primary
    if len(unique) > 1:
        rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        unique_sorted = sorted(unique, key=lambda d: rank.get(d.severity, 9))
        primary = unique_sorted[0]
        unique = unique_sorted

    heal_packages = []
    for d in unique:
        if d.suggested_action == "install_package" and d.suggested_package:
            if d.suggested_package not in heal_packages:
                heal_packages.append(d.suggested_package)

    ok = not unique
    if exit_code not in (None, 0) and not unique:
        ok = False
        primary = DiagnosedError(
            category="runtime",
            severity="medium",
            title="توقف غير طبيعي",
            summary_ar=f"انتهى العملية بكود {exit_code} بدون traceback واضح.",
            suggested_action="escalate",
            confidence=0.4,
        )
        unique = [primary]

    return ErrorContract(
        ok=ok,
        phase=phase or ("install" if install_log and not run_log else "run"),
        exit_code=exit_code,
        events=events,
        errors=unique,
        primary=primary,
        healable=bool(heal_packages),
        heal_packages=heal_packages,
        raw_install_log_tail=(install_log or "")[-2000:],
        raw_run_log_tail=(run_log or "")[-3000:],
    )


def diagnose_live_report(report: Any) -> ErrorContract:
    """Adapt a LiveRunReport-like object into ErrorContract."""
    return analyze_logs(
        run_log=getattr(report, "run_log", "") or "",
        install_log=getattr(report, "install_log", "") or "",
        phase=getattr(report, "phase", "") or "",
        exit_code=None,
        extra_errors=list(getattr(report, "errors", None) or []),
    )


class ErrorIntelligenceService:
    """Facade used by LiveRunner and future hosting monitor."""

    def analyze(
        self,
        *,
        run_log: str = "",
        install_log: str = "",
        phase: str = "",
        exit_code: int | None = None,
        extra_errors: list[str] | None = None,
    ) -> ErrorContract:
        return analyze_logs(
            run_log=run_log,
            install_log=install_log,
            phase=phase,
            exit_code=exit_code,
            extra_errors=extra_errors,
        )

    def diagnose_report(self, report: Any) -> ErrorContract:
        return diagnose_live_report(report)
