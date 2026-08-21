"""Engine gathers measurable repo facts; Grok (LLM) explains/answers from those facts."""
from __future__ import annotations

import logging
import os
from collections import Counter
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SKIP = {
    ".git", "__pycache__", ".venv", "venv", "node_modules", ".tox",
    "dist", "build", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "htmlcov", "site-packages", ".eggs",
}
_KEY_NAMES = {
    "readme.md", "readme.rst", "readme.txt", "readme",
    "main.py", "bot.py", "app.py", "run.py", "server.py",
    "requirements.txt", "pyproject.toml", "package.json", "setup.py",
    "dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".env.example", "makefile", "procfile",
}
_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt",
    ".c", ".cpp", ".h", ".cs", ".rb", ".php", ".swift", ".scala",
    ".sh", ".bash", ".sql", ".html", ".css", ".vue", ".svelte",
}


def gather_repo_dossier(
    root: Path,
    *,
    max_tree: int = 120,
    max_bytes_per_file: int = 5000,
    max_key_files: int = 14,
) -> dict[str, Any]:
    """Deterministic measurable facts — line counts, tree, key file contents."""
    root = Path(root).resolve()
    tree: list[str] = []
    key_files: dict[str, str] = {}
    ext_counts: Counter[str] = Counter()
    ext_lines: Counter[str] = Counter()
    total_files = 0
    total_lines = 0
    code_lines = 0
    largest: list[tuple[int, str]] = []

    for p in root.rglob("*"):
        try:
            if not p.is_file():
                continue
            if any(s in p.parts for s in _SKIP):
                continue
            rel = p.relative_to(root).as_posix()
            total_files += 1
            ext = p.suffix.lower() or "(no_ext)"
            ext_counts[ext] += 1

            # line count
            lines_n = 0
            try:
                # binary-ish skip for huge non-text
                if p.stat().st_size > 2_000_000:
                    pass
                else:
                    raw = p.read_bytes()
                    if b"\x00" in raw[:2048]:
                        lines_n = 0
                    else:
                        lines_n = raw.count(b"\n") + (1 if raw and not raw.endswith(b"\n") else 0)
            except Exception:
                lines_n = 0
            total_lines += lines_n
            if ext in _CODE_EXT:
                code_lines += lines_n
                ext_lines[ext] += lines_n
            largest.append((lines_n, rel))

            if len(tree) < max_tree and rel.count("/") <= 4:
                tree.append(rel)

            name = p.name.lower()
            if name in _KEY_NAMES or rel.lower() in _KEY_NAMES:
                if len(key_files) < max_key_files:
                    try:
                        key_files[rel] = p.read_text(encoding="utf-8", errors="ignore")[:max_bytes_per_file]
                    except Exception:
                        pass
        except Exception:
            continue

    largest.sort(reverse=True)
    # more py/js entry-ish files into key_files
    if len(key_files) < max_key_files:
        for _, rel in largest:
            if len(key_files) >= max_key_files:
                break
            if rel in key_files:
                continue
            low = rel.lower()
            if not any(low.endswith(x) for x in (".py", ".ts", ".js", ".md", ".toml", ".json", ".yml", ".yaml")):
                continue
            if low.count("/") > 2:
                continue
            try:
                key_files[rel] = (root / rel).read_text(encoding="utf-8", errors="ignore")[:max_bytes_per_file]
            except Exception:
                pass

    facts = {
        "total_files": total_files,
        "total_lines_all_textish": total_lines,
        "code_lines": code_lines,
        "files_by_extension": dict(ext_counts.most_common(25)),
        "lines_by_code_extension": dict(ext_lines.most_common(15)),
        "largest_files_by_lines": [
            {"path": rel, "lines": n} for n, rel in largest[:15]
        ],
    }
    return {
        "root": str(root),
        "tree": tree[:max_tree],
        "key_files": key_files,
        "facts": facts,
        "file_count_sampled": len(tree),
    }


def _dossier_prompt(dossier: dict[str, Any], *, user_question: str, url: str = "") -> str:
    facts = dossier.get("facts") or {}
    parts = [
        "أنت جوراك. عندك مواد خام مقاسة من المستودع. أجب بدقة من قسم FACTS ولا تخترع أرقاماً.",
        "لو المستخدم سأل عن عدد الأسطر أو الملفات استخدم الأرقام في FACTS حرفياً.",
        "اشرح بالعربية بوضوح. لا ترجع JSON.",
        "",
        f"سؤال المستخدم: {user_question or 'افهم المستودع'}",
    ]
    if url:
        parts.append(f"URL: {url}")
    parts.append(f"ROOT: {dossier.get('root')}")
    parts.append("")
    parts.append("=== FACTS (مقاسة بالمحرك — مصدر الحقيقة) ===")
    parts.append(f"total_files = {facts.get('total_files')}")
    parts.append(f"total_lines_all_textish = {facts.get('total_lines_all_textish')}")
    parts.append(f"code_lines = {facts.get('code_lines')}")
    parts.append(f"files_by_extension = {facts.get('files_by_extension')}")
    parts.append(f"lines_by_code_extension = {facts.get('lines_by_code_extension')}")
    parts.append(f"largest_files_by_lines = {facts.get('largest_files_by_lines')}")
    parts.append("")
    parts.append("=== TREE (عينة مسارات) ===")
    parts.append("\n".join(f"- {x}" for x in (dossier.get("tree") or [])[:80]))
    parts.append("")
    parts.append("=== KEY FILE CONTENTS ===")
    for path, body in list((dossier.get("key_files") or {}).items())[:12]:
        parts.append(f"\n--- {path} ---\n{body[:4000]}")
    return "\n".join(parts)[:28000]


def explain_repo_with_llm(
    root: Path,
    *,
    user_question: str = "",
    url: str = "",
) -> tuple[str | None, dict[str, Any]]:
    dossier = gather_repo_dossier(Path(root))
    facts = dossier.get("facts") or {}
    meta: dict[str, Any] = {
        "dossier": {
            "root": dossier.get("root"),
            "tree": dossier.get("tree"),
            "facts": facts,
            "key_file_names": list((dossier.get("key_files") or {}).keys()),
        },
        "url": url or "",
        "explainer": None,
    }
    prompt = _dossier_prompt(dossier, user_question=user_question, url=url)

    text = _freeform_completion(prompt)
    if text:
        meta["explainer"] = "groq_freeform"
        return text.strip(), meta

    try:
        from telegram_bot_engine.services.llm.facade import chat_request
        result = chat_request(prompt[:8000], context={"mode": "repo_explain", "no_tools": True})
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

    # Honest facts-only answer so questions like line-count still work without LLM
    facts_ar = (
        f"المسار: `{dossier.get('root')}`\n"
        + (f"الرابط: {url}\n" if url else "")
        + f"عدد الملفات: {facts.get('total_files')}\n"
        + f"إجمالي الأسطر (نصي): {facts.get('total_lines_all_textish')}\n"
        + f"أسطر الكود: {facts.get('code_lines')}\n"
        + f"حسب الامتداد (ملفات): {facts.get('files_by_extension')}\n"
        + f"أسطر الكود حسب الامتداد: {facts.get('lines_by_code_extension')}\n"
        + "أكبر الملفات بالأسطر:\n"
        + "\n".join(
            f"  - {x.get('path')}: {x.get('lines')}"
            for x in (facts.get("largest_files_by_lines") or [])[:10]
        )
        + "\n\n(جوراك/LLM غير متاح — الأرقام من قياس المحرك)"
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
        "llama-3.3-70b-versatile",
        "llama-3.1-70b-versatile",
        "openai/gpt-oss-20b",
    ]
    system = (
        "أنت جوراك. تجيب من FACTS والملفات المعطاة فقط. "
        "أرقام الأسطر والملفات تؤخذ من FACTS حرفياً. بالعربية. بدون JSON."
    )
    api = "https://api.groq.com/openai/v1/chat/completions"
    for source, key in keys:
        for model in models:
            try:
                resp = requests.post(
                    api,
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "temperature": 0.2,
                        "max_tokens": 2500,
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt[:22000]},
                        ],
                    },
                    timeout=float(os.getenv("GROQ_TIMEOUT") or "75"),
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
                    ((body.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                ).strip()
                if content:
                    logger.info("repo explain ok source=%s model=%s", source, model)
                    return content
            except Exception as exc:
                logger.warning("repo explain fail %s %s: %s", source, model, type(exc).__name__)
                continue
    return None
