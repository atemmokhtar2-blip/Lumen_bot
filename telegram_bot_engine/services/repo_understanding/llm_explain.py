"""Grok/LLM understands the repo; engine only supplies raw material (clone + files)."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SKIP = {".git", "__pycache__", ".venv", "venv", "node_modules", ".tox", "dist", "build"}
_KEY_NAMES = {
    "readme.md", "readme.rst", "readme.txt", "readme",
    "main.py", "bot.py", "app.py", "run.py",
    "requirements.txt", "pyproject.toml", "package.json",
    "dockerfile", "docker-compose.yml", ".env.example",
}


def gather_repo_dossier(root: Path, *, max_files: int = 80, max_bytes_per_file: int = 4000) -> dict[str, Any]:
    """Deterministic file facts only — no interpretation."""
    root = Path(root).resolve()
    tree: list[str] = []
    key_files: dict[str, str] = {}
    all_py: list[str] = []

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(s in p.parts for s in _SKIP):
            continue
        rel = p.relative_to(root).as_posix()
        if rel.count("/") <= 3:
            tree.append(rel)
        if len(tree) >= max_files:
            break

    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(s in p.parts for s in _SKIP):
            continue
        rel = p.relative_to(root).as_posix()
        name = p.name.lower()
        if name in _KEY_NAMES or rel.lower() in _KEY_NAMES:
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")[:max_bytes_per_file]
                key_files[rel] = text
            except Exception:
                pass
        if p.suffix == ".py" and rel.count("/") <= 2:
            all_py.append(rel)
        if len(key_files) >= 12:
            break

    # fill more py snippets if few key files
    if len(key_files) < 6:
        for rel in all_py[:8]:
            if rel in key_files:
                continue
            try:
                text = (root / rel).read_text(encoding="utf-8", errors="ignore")[:2500]
                key_files[rel] = text
            except Exception:
                pass
            if len(key_files) >= 8:
                break

    return {
        "root": str(root),
        "tree": tree[:max_files],
        "key_files": key_files,
        "python_files_top": all_py[:40],
        "file_count_sampled": len(tree),
    }


def _dossier_prompt(dossier: dict[str, Any], *, user_question: str, url: str = "") -> str:
    parts = [
        "أنت جوراك. مهمتك: تفهم المستودع من المواد الخام التالية وتشرح للمستخدم بالعربية بوضوح.",
        "لا تخترع ملفات أو مكتبات غير موجودة في المواد. لو معلومة ناقصة قول إنها غير ظاهرة.",
        "اشرح: الغرض، الهيكل، نقاط التشغيل، التقنيات، وكيف يستخدمه المستخدم عملياً.",
        "",
        f"سؤال المستخدم: {user_question or 'افهم المستودع واشرحه لي'}",
    ]
    if url:
        parts.append(f"رابط المستودع: {url}")
    parts.append(f"المسار المحلي: {dossier.get('root')}")
    parts.append("شجرة ملفات (عينة):")
    parts.append("\n".join(f"- {x}" for x in (dossier.get("tree") or [])[:60]))
    parts.append("محتوى ملفات مهمة:")
    for path, body in list((dossier.get("key_files") or {}).items())[:10]:
        parts.append(f"\n--- {path} ---\n{body[:3500]}")
    return "\n".join(parts)[:24000]


def explain_repo_with_llm(
    root: Path,
    *,
    user_question: str = "",
    url: str = "",
) -> tuple[str | None, dict[str, Any]]:
    """
    Engine gathers dossier; LLM (Grok path via Groq chat completions) explains.
    Returns (explanation_text or None, meta).
    """
    dossier = gather_repo_dossier(Path(root))
    meta: dict[str, Any] = {
        "dossier": {
            "root": dossier.get("root"),
            "tree": dossier.get("tree"),
            "python_files_top": dossier.get("python_files_top"),
            "key_file_names": list((dossier.get("key_files") or {}).keys()),
            "file_count_sampled": dossier.get("file_count_sampled"),
        },
        "url": url or "",
        "explainer": None,
    }
    prompt = _dossier_prompt(dossier, user_question=user_question, url=url)

    # Direct free-text completion (not the JSON action chat schema)
    text = _freeform_completion(prompt)
    if text:
        meta["explainer"] = "groq_freeform"
        return text.strip(), meta

    # Fallback: facade chat_request (may return structured JSON)
    try:
        from telegram_bot_engine.services.llm.facade import chat_request
        result = chat_request(
            prompt[:8000],
            context={"mode": "repo_explain", "no_tools": True},
        )
        if isinstance(result, dict):
            answer = (
                result.get("answer")
                or result.get("message")
                or result.get("reply")
                or result.get("content")
                or ""
            )
            if answer:
                meta["explainer"] = "chat_request"
                return str(answer).strip(), meta
    except Exception as exc:
        logger.warning("chat_request explain failed: %s", exc)
        meta["chat_request_error"] = type(exc).__name__

    # Last resort: honest engine stub so user is not lied to
    tree = dossier.get("tree") or []
    keys = list((dossier.get("key_files") or {}).keys())
    stub = (
        "تم جمع ملفات المستودع بواسطة المحرك، لكن نموذج الشرح (جوراك/LLM) غير متاح حالياً.\n"
        f"• المسار: `{dossier.get('root')}`\n"
        + (f"• الرابط: {url}\n" if url else "")
        + f"• عينة ملفات: {', '.join(tree[:15])}\n"
        + (f"• ملفات مقروءة: {', '.join(keys[:8])}\n" if keys else "")
        + "فعّل GROQ_API_KEY (أو مزود الشات) حتى يشرح جوراك المستودع بنفسه."
    )
    meta["explainer"] = "engine_facts_only"
    return stub, meta


def _freeform_completion(prompt: str) -> str | None:
    """Groq OpenAI-compatible free text — Grok-style understanding layer."""
    try:
        import requests
        from telegram_bot_engine.services.llm.key_pool import groq_keys, mark_groq_cooldown
    except Exception:
        return None

    keys = []
    try:
        keys = groq_keys()
    except Exception:
        raw = (os.getenv("GROQ_API_KEY") or "").strip()
        if raw:
            keys = [("env", raw)]
    if not keys:
        return None

    models_env = (os.getenv("GROQ_MODEL") or os.getenv("GROQ_CHAT_MODEL") or "").strip()
    models = [m.strip() for m in models_env.split(",") if m.strip()] or [
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "openai/gpt-oss-20b",
    ]
    system = (
        "أنت جوراك. تفهم المستودعات من مواد خام فقط وتشرح للمستخدم بالعربية "
        "بأسلوب واضح ومباشر. لا تخترع. لا ترجع JSON — اكتب شرحاً مفيداً فقط."
    )
    url = "https://api.groq.com/openai/v1/chat/completions"
    for source, key in keys:
        for model in models:
            try:
                resp = requests.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": model,
                        "temperature": 0.35,
                        "max_tokens": 2500,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt[:20000]},
                        ],
                    },
                    timeout=float(os.getenv("GROQ_TIMEOUT") or "60"),
                )
                if resp.status_code in {401, 403, 429}:
                    try:
                        mark_groq_cooldown(source)
                    except Exception:
                        pass
                    continue
                if resp.status_code >= 400:
                    logger.warning("repo explain HTTP %s: %s", resp.status_code, resp.text[:160])
                    continue
                body = resp.json()
                content = (
                    ((body.get("choices") or [{}])[0].get("message") or {}).get("content")
                    or ""
                ).strip()
                if content:
                    logger.info("repo explain ok source=%s model=%s", source, model)
                    return content
            except Exception as exc:
                logger.warning("repo explain failed source=%s model=%s: %s", source, model, type(exc).__name__)
                continue
    return None
