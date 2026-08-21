"""Engine runs measurable tools; Grok answers only from tool outputs."""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from .repo_tools import run_core_toolkit, toolkit_to_prompt_block, run_tool

logger = logging.getLogger(__name__)


def gather_repo_dossier(root: Path, **kwargs: Any) -> dict[str, Any]:
    """Backward-compatible dossier built from tools."""
    root = Path(root).resolve()
    stats = run_tool("stats", root)
    tree = run_tool("tree", root)
    largest = run_tool("largest_files", root)
    readme = run_tool("readme", root)
    key_files: dict[str, str] = {}
    if readme.get("content"):
        key_files[str(readme.get("path") or "README")] = str(readme.get("content") or "")[:5000]
    for item in (largest.get("files") or [])[:6]:
        path = item.get("path") or ""
        if path and path not in key_files:
            rf = run_tool("read_file", root, path=path, max_chars=3000)
            if rf.get("ok") and rf.get("content"):
                key_files[path] = str(rf.get("content") or "")
    facts = {
        "total_files": stats.get("total_files"),
        "total_lines_all_textish": stats.get("total_lines"),
        "code_lines": stats.get("code_lines"),
        "files_by_extension": stats.get("files_by_extension"),
        "lines_by_code_extension": stats.get("code_lines_by_extension"),
        "largest_files_by_lines": largest.get("files") or [],
    }
    return {
        "root": str(root),
        "tree": tree.get("paths") or [],
        "key_files": key_files,
        "facts": facts,
        "file_count_sampled": len(tree.get("paths") or []),
    }


def explain_repo_with_llm(
    root: Path,
    *,
    user_question: str = "",
    url: str = "",
) -> tuple[str | None, dict[str, Any]]:
    root = Path(root).resolve()
    tool_results = run_core_toolkit(root, user_question=user_question or "")
    tools_block = toolkit_to_prompt_block(tool_results)
    stats = next((r for r in tool_results if r.get("tool") == "stats"), {})

    meta: dict[str, Any] = {
        "dossier": {
            "root": str(root),
            "facts": {
                "total_files": stats.get("total_files"),
                "total_lines_all_textish": stats.get("total_lines"),
                "code_lines": stats.get("code_lines"),
                "files_by_extension": stats.get("files_by_extension"),
                "lines_by_code_extension": stats.get("code_lines_by_extension"),
            },
            "tools_run": [r.get("tool") for r in tool_results],
        },
        "url": url or "",
        "explainer": None,
        "tool_results_count": len(tool_results),
    }

    prompt = "\n".join([
        "أنت جوراك مربوط بالمستودع النشط اللي المستخدم سحبه.",
        "جاوب من مخرجات أدوات المحرك فقط (TOOL_RESULTS) — دي الحقيقة الوحيدة.",
        "ممنوع تخترع ملفات أو مكتبات أو أرقام أو محتوى غير موجود في TOOL_RESULTS.",
        "لو المستخدم طلب ملف (هات/اعرض/اقرأ): استخدم نتائج find_files و read_file واعرض المحتوى أو المسار.",
        "لو السؤال غير متوقع: استنتج من TOOL_RESULTS فقط؛ لو مش موجود قول بصراحة: غير موجود في نتائج الأدوات.",
        "جاوب بالعربية بوضوح واختصار مفيد.",
        "",
        f"سؤال المستخدم: {user_question or 'افهم المستودع'}",
        f"ROOT: {root}",
        f"URL: {url or '(none)'}",
        "",
        "=== TOOL_RESULTS (مصدر الحقيقة) ===",
        tools_block,
    ])

    text = _freeform_completion(prompt)
    if text:
        meta["explainer"] = "groq_freeform"
        return text.strip(), meta

    # facts-only fallback
    facts_ar = (
        f"ROOT: `{root}`\n"
        + (f"URL: {url}\n" if url else "")
        + f"total_files={stats.get('total_files')}\n"
        + f"total_lines={stats.get('total_lines')}\n"
        + f"code_lines={stats.get('code_lines')}\n"
        + f"files_by_extension={stats.get('files_by_extension')}\n"
        + f"tools_run={[r.get('tool') for r in tool_results]}\n"
        + "(Grok LLM unavailable — engine tool numbers only)"
    )
    meta["explainer"] = "engine_facts_only"
    return facts_ar, meta


def _freeform_completion(prompt: str) -> str | None:
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
        "openai/gpt-oss-20b",
        "llama-3.1-8b-instant",
        "gemma2-9b-it",
    ]
    system = (
        "You are Grok bound to the user's cloned repository. "
        "Answer ONLY from TOOL_RESULTS (engine measurements). Never invent files or numbers. "
        "If the user asked for a file, quote path + content from read_file/find_files results. "
        "Arabic preferred when the user writes Arabic. No JSON wrapper."
    )
    # Large context: allow generous prompt window (models with big context use more)
    try:
        prompt_cap = max(12000, int(os.getenv("REPO_EXPLAIN_PROMPT_CHARS") or "48000"))
    except ValueError:
        prompt_cap = 48000
    try:
        max_tok = max(800, int(os.getenv("REPO_EXPLAIN_MAX_TOKENS") or "4096"))
    except ValueError:
        max_tok = 4096
    api = "https://api.groq.com/openai/v1/chat/completions"
    for source, key in keys:
        for model in models:
            try:
                resp = requests.post(
                    api,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "temperature": 0.15,
                        "max_tokens": max_tok,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt[:prompt_cap]},
                        ],
                    },
                    timeout=float(os.getenv("GROQ_TIMEOUT") or "90"),
                )
                if resp.status_code in {401, 403, 429}:
                    try:
                        mark_groq_cooldown(source)
                    except Exception:
                        pass
                    continue
                if resp.status_code >= 400:
                    logger.warning("repo explain HTTP %s: %s", resp.status_code, resp.text[:180])
                    continue
                body = resp.json()
                content = (
                    ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                ).strip()
                if content:
                    logger.info("repo explain ok source=%s model=%s", source, model)
                    return content
            except Exception as exc:
                logger.warning("repo explain fail %s %s: %s", source, model, type(exc).__name__)
                continue
    return None
