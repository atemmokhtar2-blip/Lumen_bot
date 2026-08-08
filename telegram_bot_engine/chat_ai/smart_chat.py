"""
SmartChat — g4f-powered guidance layer (chat only).

Responsibilities:
  - Understand user intent from minimal wording (Arabic / English).
  - Ask clarifying questions when needed.
  - Recommend the correct system capability (or return a helpful reply).
  - NEVER generate code, NEVER touch formal_engine, NEVER invent success.

g4f is allowed only in chat_ai (SmartChat + Understanding-AI). Never inside formal_engine.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("ai_agent_7h_bot.chat_ai")

# ---------------------------------------------------------------------------
# System knowledge (mirrors ChatRouter capabilities — keep in sync)
# ---------------------------------------------------------------------------

_CAPABILITIES_TEXT = """
القدرات المتاحة في النظام (يجب توجيه المستخدم إليها فقط):

1. generate_bot — توليد بوت
   فهم مواصفة وتوليد مشروع بوت تليجرام من وصف المستخدم.

2. clone_repo — سحب مستودع
   سحب مستودع Git (GitHub/GitLab) وفهمه. يحتاج رابط + توكن إن كان خاصاً.

3. host_start — بدء الاستضافة
   تشغيل البوت كخدمة استضافة طويلة الأمد (يحتاج مشروع جاهز + توكن).

4. host_stop — إيقاف الاستضافة
5. host_status — حالة الاستضافة
6. host_diagnose — تشخيص الاستضافة

7. static_analysis — تحليل استاتيكي
8. package_health — صحة الحزم
9. upgrade_recommend — توصيات الترقية
10. upgrade_apply — تطبيق ترقيات آمنة
11. repo_develop — تطوير المستودع النشط
12. live_run — تشغيل حي قصير ب توكن
13. help — مساعدة وشرح القدرات
"""

_SYSTEM_PROMPT = f"""أنت مساعد ذكي لبوت "AI Agent 7h Bot". دورك **الشات فقط**.

قواعد صارمة جداً (لا تكسرها أبداً):
1. أنت **مترجم وموجه** فقط. تفهم نية المستخدم من أقل كلمة وتوجهه للمسار الصحيح.
2. **ممنوع تماماً** توليد أي كود أو ملفات أو مشاريع.
3. **ممنوع تماماً** الادعاء أنك ولّدت بوت أو عدّلت ملفات.
4. إذا أراد المستخدم عمل بوت → اسأله أسئلة توضيحية قصيرة وواضحة (نوع البوت، الأوامر، اللغة...).
5. إذا فهمت النية بوضوح → أرجع توصية بالمسار الصحيح.
6. ردودك دائماً بالعربية الفصحى البسيطة أو العامية المصرية الواضحة.
7. كن مختصراً وودوداً ومباشراً.

{_CAPABILITIES_TEXT}

طريقة الرد المطلوبة (التزم بها بدقة):
- إذا كنت تحتاج توضيحاً من المستخدم → أرجع JSON بهذا الشكل فقط:
{{"type": "reply", "text": "سؤالك أو ردك هنا"}}

- إذا فهمت النية بوضوح وتريد توجيه النظام → أرجع JSON بهذا الشكل فقط:
{{"type": "route", "capability_id": "generate_bot", "confidence": 0.85, "params": {{}}, "text": "رسالة قصيرة للمستخدم قبل التنفيذ"}}

capability_id يجب أن يكون واحداً من القائمة أعلاه فقط.
لا تكتب أي نص خارج الـ JSON.
"""


@dataclass
class SmartChatResult:
    """Result from the smart chat layer."""
    type: str  # "reply" | "route" | "error"
    text: str = ""
    capability_id: str = ""
    confidence: float = 0.0
    params: dict[str, Any] = field(default_factory=dict)
    raw: str = ""


def _parse_response(content: str) -> SmartChatResult:
    """Extract JSON from model output robustly."""
    content = (content or "").strip()
    if not content:
        return SmartChatResult(type="error", text="لم أتمكن من الفهم. حاول صياغة أوضح.")

    # Try direct JSON
    try:
        data = json.loads(content)
        return _from_dict(data, content)
    except json.JSONDecodeError:
        pass

    # Try extract first JSON object
    match = re.search(r"\{[\s\S]*\}", content)
    if match:
        try:
            data = json.loads(match.group(0))
            return _from_dict(data, content)
        except json.JSONDecodeError:
            pass

    # Fallback: treat whole text as a helpful reply
    return SmartChatResult(type="reply", text=content[:1500], raw=content)


def _from_dict(data: dict, raw: str) -> SmartChatResult:
    t = str(data.get("type", "reply")).lower().strip()
    if t == "route":
        cap = str(data.get("capability_id", "")).strip()
        conf = float(data.get("confidence", 0.7) or 0.7)
        params = data.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        text = str(data.get("text", "") or "")
        if not cap:
            return SmartChatResult(type="reply", text=text or "وضح أكثر من فضلك.", raw=raw)
        return SmartChatResult(
            type="route",
            text=text,
            capability_id=cap,
            confidence=min(1.0, max(0.0, conf)),
            params=params,
            raw=raw,
        )
    # default reply
    text = str(data.get("text", "") or data.get("message", "") or "")
    return SmartChatResult(type="reply", text=text or "وضح أكثر من فضلك.", raw=raw)


def smart_chat_reply(
    user_text: str,
    *,
    conversation_hint: str = "",
    timeout: int = 45,
) -> SmartChatResult:
    """
    Call Hugging Face Inference Providers and return a structured result.

    On any failure it returns a safe Arabic reply (never raises to the caller).
    """
    user_text = (user_text or "").strip()
    if len(user_text) < 1:
        return SmartChatResult(type="reply", text="اكتب رسالتك وسأساعدك.")

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
    ]
    if conversation_hint:
        messages.append({
            "role": "system",
            "content": f"سياق إضافي: {conversation_hint[:400]}",
        })
    messages.append({"role": "user", "content": user_text})

    try:
        from .hf_provider import chat

        content, model = chat(
            messages,
            timeout=timeout,
            max_tokens=900,
            temperature=0.1,
            json_mode=True,
        )
        result = _parse_response(content)
        logger.info("smart_chat provider=huggingface model=%s", model)
        logger.info(
            "smart_chat type=%s cap=%s conf=%.2f",
            result.type,
            result.capability_id,
            result.confidence,
        )
        return result
    except Exception as e:
        logger.exception("Hugging Face smart_chat failed: %s", e)
        return SmartChatResult(
            type="error",
            text=(
                "حدث خطأ مؤقت في المساعد الذكي.\n"
                "جرّب صياغة أوضح أو استخدم الأوامر المباشرة مثل:\n"
                "• «اعمل بوت ...»\n"
                "• «اسحب المستودع ...»\n"
                "• «مساعدة»"
            ),
            raw=str(e)[:200],
        )
