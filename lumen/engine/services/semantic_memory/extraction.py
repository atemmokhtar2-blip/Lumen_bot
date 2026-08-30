"""Memory extraction & update pipeline (Mem0 Algorithm 1).

After a conversational exchange (user message + assistant reply), this module:
  1. extracts salient durable facts (preferences, decisions, project notes,
     instructions, profile) via an LLM,
  2. for each candidate fact, retrieves the top-s semantically similar memories,
  3. classifies the operation (ADD / UPDATE / DELETE / NOOP) via an LLM tool call,
  4. executes the operation against SemanticMemoryStore.

This is what makes the engine "remember" each user across sessions without
replaying the whole transcript.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from .store import MemoryRecord, get_semantic_store

logger = logging.getLogger(__name__)

_EXTRACT_TOP_S = 5  # similar memories to consider for update classification


_EXTRACT_SYSTEM = """\
أنت نظام استخراج ذاكرة لمساعد ذكي يبني بوتات للمستخدمين.
مهمتك: استخراج الحقائق الدائمة المفيدة التي يستحسن تذكرها لاحقًا عن المستخدم
أو عن مشاريعه/بوتاته. استخرج فقط ما يستحق التذكر طويلًا — لا تُخزّن سلامًا
ولا أسئلة عابرة ولا ردود وصفية عامة.

لكل حقيقة، أعطِ:
- content: الحقيقة بصيغة مختصرة واضحة (يفضّل العربية إذا كان المستخدم يتحدث عربية)
- kind: نوعها، أحد: preference | decision | fact | project_note | instruction | profile

أمثلة:
- "المستخدم يفضّل بوتات تليجرام بلغة Python" → kind=preference
- "قرر المستخدم إزالة زر المساعدة من البوت" → kind=decision
- "المشروع اسمه MyBot ويستخدم InlineKeyboard" → kind=project_note
- "لا تضف logging معقد — يريده بسيط" → kind=instruction
- "المستخدم مطور ومبتدئ في async" → kind=profile

أعد النتيجة JSON فقط بالصيغة:
{"facts": [{"content": "...", "kind": "..."}]}

إن لم توجد حقائق تستحق التذكر، أعد: {"facts": []}
"""

_UPDATE_SYSTEM = """\
أنت نظام تحديث ذاكرة. أمامك:
- fact: حقيقة جديدة مُستخرجة
- existing: قائمة ذكريات موجودة مشابهة دلاليًا (id + content)

قرر العملية الواجبة عبر JSON:
- "ADD": الحقيقة جديدة تمامًا (لا توجد مشابهة كافية)
- "UPDATE": توجد ذاكرة مشابهة ويجب استبدالها/إثراؤها بهذه (اذكر target_id)
- "DELETE": الحقيقة الجديدة تناقض ذاكرة موجودة وتبطلها (اذكر target_id)
- "NOOP": الحقيقة موجودة فعليًا أو لا قيمة لها

أعد JSON فقط بالصيغة:
{"operation": "ADD|UPDATE|DELETE|NOOP", "target_id": "...", "reason": "..."}
"""


def _llm_json(system: str, user: str, *, timeout: float = 30.0) -> dict[str, Any]:
    """Call the project chat LLM with a custom system prompt for JSON extraction.

    Uses the Groq/Grok HTTP path directly (temperature low) so we get structured
    JSON independent of the consumer-facing chat system prompt.
    """
    import os
    # Prefer Groq (low-latency, JSON-friendly). Fall back to Gemini key if present.
    groq_keys_raw = os.getenv("GROQ_API_KEY") or ""
    gemini_key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()

    def _try_groq() -> dict[str, Any] | None:
        if not groq_keys_raw:
            return None
        try:
            import requests
            keys = [k.strip() for k in groq_keys_raw.split(",") if k.strip()]
            models = (os.getenv("GROQ_CHAT_MODEL") or "llama-3.3-70b-versatile,openai/gpt-oss-20b").split(",")
            models = [m.strip() for m in models if m.strip()]
            url = "https://api.groq.com/openai/v1/chat/completions"
            for key in keys:
                for model in models:
                    try:
                        r = requests.post(url, headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        }, json={
                            "model": model,
                            "temperature": 0.1,
                            "max_tokens": 900,
                            "messages": [
                                {"role": "system", "content": system},
                                {"role": "user", "content": user[:6000]},
                            ],
                        }, timeout=timeout)
                        if r.status_code >= 400:
                            continue
                        body = r.json()
                        content = (body.get("choices") or [{}])[0].get("message", {}).get("content", "")
                        return _parse_json(content)
                    except Exception:
                        continue
        except Exception:
            logger.debug("groq extraction call failed", exc_info=True)
        return None

    def _try_gemini() -> dict[str, Any] | None:
        if not gemini_key:
            return None
        try:
            import requests
            model = (os.getenv("GEMINI_MODEL") or "gemini-2.0-flash")
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
            r = requests.post(url, headers={"Content-Type": "application/json"}, json={
                "contents": [{"parts": [{"text": system + "\n\n" + user[:6000]}]}],
                "generationConfig": {"temperature": 0.1, "maxOutputTokens": 900},
            }, timeout=timeout)
            if r.status_code >= 400:
                return None
            body = r.json()
            parts = body.get("candidates", [{}])[0].get("content", {}).get("parts", [])
            content = "".join(p.get("text", "") for p in parts)
            return _parse_json(content)
        except Exception:
            logger.debug("gemini extraction call failed", exc_info=True)
        return None

    for fn in (_try_groq, _try_gemini):
        out = fn()
        if isinstance(out, dict):
            return out
    return {}


def _parse_json(content: str) -> dict[str, Any]:
    if not content:
        return {}
    s = content.strip()
    # strip code fences
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    # find first {...} block
    start = s.find("{")
    end = s.rfind("}")
    if start != -1 and end != -1 and end > start:
        s = s[start:end + 1]
    try:
        return json.loads(s)
    except Exception:
        return {}


def extract_facts(
    user_message: str,
    assistant_message: str,
    *,
    recent_summary: str = "",
    recent_turns: list[dict[str, str]] | None = None,
) -> list[dict[str, str]]:
    """LLM-based fact extraction from one exchange."""
    ctx_lines = []
    if recent_summary:
        ctx_lines.append(f"ملخص المحادثة السابقة:\n{recent_summary[:1200]}")
    if recent_turns:
        for t in recent_turns[-6:]:
            role = t.get("role", "?")
            txt = (t.get("content") or "")[:300]
            ctx_lines.append(f"{role}: {txt}")
    ctx = "\n".join(ctx_lines) if ctx_lines else "(لا سياق سابق)"
    user_prompt = (
        f"{ctx}\n\n"
        f"=== المحادثة الحالية ===\n"
        f"المستخدم: {user_message[:2500]}\n"
        f"Lumen: {assistant_message[:2500]}\n\n"
        f"استخرج الحقائق الدائمة:"
    )
    out = _llm_json(_EXTRACT_SYSTEM, user_prompt)
    facts = out.get("facts") or []
    clean: list[dict[str, str]] = []
    seen: set[str] = set()
    for f in facts:
        if not isinstance(f, dict):
            continue
        content = str(f.get("content") or "").strip()
        if not content:
            continue
        kind = str(f.get("kind") or "fact").strip().lower()
        if kind not in {"preference", "decision", "fact",
                        "project_note", "instruction", "profile"}:
            kind = "fact"
        key = content.lower()[:120]
        if key in seen:
            continue
        seen.add(key)
        clean.append({"content": content[:500], "kind": kind})
    return clean


def _classify_update(
    fact: dict[str, str],
    similar: list[MemoryRecord],
) -> dict[str, Any]:
    """Decide ADD/UPDATE/DELETE/NOOP for a candidate fact (LLM tool-call)."""
    if not similar:
        return {"operation": "ADD", "target_id": "", "reason": "no_similar"}
    existing_lines = []
    for rec in similar[:_EXTRACT_TOP_S]:
        existing_lines.append(f'- id={rec.id} | kind={rec.kind} | content="{rec.content}"')
    user_prompt = (
        f"fact:\n{fact.get('content','')}\n\n"
        f"existing (similar):\n" + "\n".join(existing_lines) + "\n\n"
        f"قرر العملية:"
    )
    out = _llm_json(_UPDATE_SYSTEM, user_prompt)
    op = str(out.get("operation") or "").strip().upper()
    if op not in {"ADD", "UPDATE", "DELETE", "NOOP"}:
        return {"operation": "ADD", "target_id": "", "reason": "unrecognized"}
    target_id = str(out.get("target_id") or "").strip()
    if op in {"UPDATE", "DELETE"} and target_id:
        # validate target id belongs to the similar set
        ids = {r.id for r in similar}
        if target_id not in ids:
            op = "ADD"
            target_id = ""
    return {"operation": op, "target_id": target_id,
            "reason": str(out.get("reason") or "")[:200]}


def ingest_exchange(
    *,
    user_id: int,
    user_message: str,
    assistant_message: str,
    project_id: str = "",
    recent_summary: str = "",
    recent_turns: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Full Mem0-style ingest: extract → classify → apply.

    Returns a summary of operations applied.
    """
    store = get_semantic_store()
    facts = extract_facts(
        user_message, assistant_message,
        recent_summary=recent_summary, recent_turns=recent_turns,
    )
    ops = {"add": 0, "update": 0, "delete": 0, "noop": 0, "facts": len(facts)}
    applied: list[dict[str, str]] = []
    for fact in facts:
        content = fact["content"]
        kind = fact["kind"]
        # retrieve similar existing memories for this fact
        similar = [
            r for r, _ in store.semantic_search(
                user_id=user_id, query=content,
                project_id=project_id, top_k=_EXTRACT_TOP_S, min_score=0.55,
            )
        ]
        decision = _classify_update(fact, similar)
        op = decision["operation"]
        meta = {"reason": decision.get("reason", ""), "source": "ingest"}
        if op == "ADD":
            rec = store.add(user_id=user_id, content=content, kind=kind,
                            project_id=project_id, meta=meta)
            if rec:
                ops["add"] += 1
                applied.append({"op": "ADD", "id": rec.id, "content": content[:80]})
        elif op == "UPDATE" and decision["target_id"]:
            ok = store.update(decision["target_id"], content=content,
                              kind=kind, meta=meta)
            if ok:
                ops["update"] += 1
                applied.append({"op": "UPDATE", "id": decision["target_id"],
                                "content": content[:80]})
            else:
                rec = store.add(user_id=user_id, content=content, kind=kind,
                                project_id=project_id, meta=meta)
                if rec:
                    ops["add"] += 1
        elif op == "DELETE" and decision["target_id"]:
            ok = store.delete(decision["target_id"])
            if ok:
                ops["delete"] += 1
                applied.append({"op": "DELETE", "id": decision["target_id"]})
        else:
            ops["noop"] += 1
    return {"operations": ops, "applied": applied}


__all__ = [
    "extract_facts",
    "ingest_exchange",
    "get_semantic_store",
]
