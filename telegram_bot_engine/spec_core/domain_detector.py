"""Multi-domain detector for complex free-text bot requests.

Returns domain ids that map onto existing preset / capability packs.
Scores are keyword-count based (zero-AI, deterministic).

Expanded for modern verticals: IoT, blockchain, AI/ML, DevOps, healthcare,
education, finance, logistics, gaming, social, marketplace, etc.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainHit:
    domain: str
    score: float
    matched: tuple[str, ...]


DOMAINS: dict[str, dict[str, Any]] = {
    "cybersecurity": {
        "keywords": (
            "security", "cyber", "cybersecurity", "cyberguard", "أمن", "امن", "سيبراني",
            "فحص أمني", "ثغرة", "phishing", "تصيد", "تصيّد", "dns", "tls", "ssl",
            "spf", "dmarc", "mx records", "security headers", "domain scan",
            "website scan", "soc", "incident", "vulnerability", "pentest",
            "certificate", "شهادة ssl", "نصائح أمان", "توعية أمنية",
        ),
        "weight": 3.0,
        "min_score": 1,
        "preset": "security_ops",
    },
    "iot": {
        "keywords": (
            "iot", "إنترنت الأشياء", "انترنت الاشياء", "أجهزة ذكية", "اجهزة ذكية",
            "smart devices", "smart home", "sensors", "حساسات", "مستشعرات",
            "mqtt", "بروتوكول mqtt", "home automation", "أتمتة منزلية", "اتمتة منزلية",
            "arduino", "esp32", "raspberry", "raspberry pi", "real-time data",
            "بيانات لحظية", "device registry", "سجل أجهزة", "telemetry", "تلمتري",
        ),
        "weight": 2.6,
        "min_score": 1,
        "preset": "iot",
    },
    "blockchain": {
        "keywords": (
            "blockchain", "بلوك تشين", "بلوكتشين", "سلسلة الكتل",
            "crypto", "عملة رقمية", "عملات مشفرة", "cryptocurrency",
            "bitcoin", "بيتكوين", "ethereum", "إيثريوم", "ايثيريوم",
            "smart contract", "عقد ذكي", "nft", "رموز غير قابلة",
            "defi", "تمويل لامركزي", "web3", "on-chain", "token",
        ),
        "weight": 2.5,
        "min_score": 1,
        "preset": "blockchain",
    },
    "ai_ml": {
        "keywords": (
            "ai", "ذكاء اصطناعي", "الذكاء الاصطناعي", "machine learning", "تعلم آلي",
            "chatgpt", "gpt", "openai", "nlp", "معالجة اللغة", "neural", "شبكة عصبية",
            "deep learning", "تعلم عميق", "image recognition", "تعرف على الصور",
            "sentiment", "تحليل المشاعر", "llm", "prompt", "embeddings",
        ),
        "weight": 2.2,
        "min_score": 2,
        "preset": "ai_assist",
    },
    "devops": {
        "keywords": (
            "devops", "docker", "حاوية", "container", "kubernetes", "k8s",
            "ci/cd", "cicd", "تكامل مستمر", "نشر مستمر", "deployment", "نشر",
            "aws", "azure", "google cloud", "gcp", "monitoring", "مراقبة",
            "logging", "سجلات", "pipeline", "helm", "terraform", "infra",
        ),
        "weight": 2.4,
        "min_score": 1,
        "preset": "devops",
    },
    "healthcare": {
        "keywords": (
            "طبي", "صحي", "medical", "healthcare", "hospital", "مستشفى",
            "عيادة", "clinic", "doctor", "دكتور", "طبيب", "patient", "مريض",
            "appointment", "موعد", "prescription", "وصفة", "medical records",
            "سجلات طبية", "pharmacy", "صيدلية", "lab", "مختبر",
        ),
        "weight": 2.3,
        "min_score": 1,
        "preset": "clinic",
    },
    "education": {
        "keywords": (
            "تعليم", "تعلم", "education", "learning", "course", "دورة", "كورس",
            "quiz", "اختبار", "امتحان", "certificate", "شهادة", "student", "طالب",
            "teacher", "معلم", "lms", "نظام إدارة التعلم", "lesson", "درس", "homework",
        ),
        "weight": 2.0,
        "min_score": 1,
        "preset": "education",
    },
    "ecommerce": {
        "keywords": (
            "shop", "store", "متجر", "بيع", "products", "منتجات", "ecommerce",
            "سلة", "cart", "كتالوج", "catalog", "checkout", "طلب",
        ),
        "weight": 1.8,
        "min_score": 2,
        "preset": "shop",
    },
    "marketplace": {
        "keywords": (
            "marketplace", "سوق متعدد", "multi-vendor", "بائعين", "vendor",
            "escrow", "ضمان", "affiliate", "عمولة", "dropshipping", "دروب",
            "auction", "مزاد", "commission",
        ),
        "weight": 2.3,
        "min_score": 1,
        "preset": "marketplace",
    },
    "finance": {
        "keywords": (
            "مالية", "finance", "محاسبة", "accounting", "bank", "بنك", "مصرف",
            "invoice", "فاتورة", "expense", "مصروف", "budget", "ميزانية",
            "tax", "ضريبة", "ledger", "دفتر", "kyc", "aml", "treasury",
        ),
        "weight": 2.2,
        "min_score": 1,
        "preset": "finance",
    },
    "logistics": {
        "keywords": (
            "لوجستيات", "logistics", "شحن", "shipping", "delivery", "توصيل",
            "warehouse", "مستودع", "مخزن", "inventory", "مخزون", "tracking",
            "تتبع", "fleet", "أسطول", "courier", "مندوب",
        ),
        "weight": 2.1,
        "min_score": 1,
        "preset": "logistics",
    },
    "gaming": {
        "keywords": (
            "game", "لعبة", "ألعاب", "العاب", "multiplayer", "متعدد اللاعبين",
            "leaderboard", "لوحة المتصدرين", "achievement", "إنجاز", "انجاز",
            "tournament", "بطولة", "match", "مباراة", "xp", "level up",
        ),
        "weight": 2.0,
        "min_score": 1,
        "preset": "gaming",
    },
    "social": {
        "keywords": (
            "social media", "وسائل التواصل", "community", "مجتمع", "forum", "منتدى",
            "post", "منشور", "comment", "تعليق", "like", "إعجاب", "اعجاب",
            "feed", "news feed", "timeline",
        ),
        "weight": 1.7,
        "min_score": 2,
        "preset": "community",
    },
    "projects": {
        "keywords": (
            "project", "projects", "مشروع", "مشاريع", "project management",
            "إدارة مشاريع", "ادارة مشاريع",
        ),
        "weight": 1.6,
        "min_score": 1,
        "preset": "tasks",
    },
    "saas": {
        "keywords": (
            "saas", "multi-tenant", "workspace", "tenant", "rbac", "quota", "seats",
            "منصة برمجية", "feature flag",
        ),
        "weight": 2.2,
        "min_score": 1,
        "preset": "saas",
    },
    "hr": {
        "keywords": (
            "hr", "موارد بشرية", "إجازة", "اجازة", "حضور", "checkin", "موظف",
            "employee", "payroll", "رواتب",
        ),
        "weight": 1.8,
        "min_score": 1,
        "preset": "hr",
    },
    "fitness": {
        "keywords": (
            "fitness", "gym", "جيم", "رياضة", "workout", "تمارين", "عضوية نادي",
        ),
        "weight": 1.9,
        "min_score": 1,
        "preset": "fitness",
    },
}


def detect(text: str, *, limit: int = 8) -> list[str]:
    return [h.domain for h in detect_detailed(text, limit=limit)]


def detect_detailed(text: str, *, limit: int = 8) -> list[DomainHit]:
    t = (text or "").lower()
    hits: list[DomainHit] = []
    for domain, cfg in DOMAINS.items():
        matched = tuple(kw for kw in cfg["keywords"] if kw in t)
        raw = float(len(matched))
        if raw < float(cfg.get("min_score", 1)):
            continue
        score = raw * float(cfg.get("weight", 1.0))
        hits.append(DomainHit(domain=domain, score=score, matched=matched))
    hits.sort(key=lambda h: (-h.score, h.domain))
    return hits[:limit]


def domains_to_presets(domains: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for d in domains:
        preset = (DOMAINS.get(d) or {}).get("preset")
        if preset and preset not in seen:
            seen.add(preset)
            out.append(str(preset))
    return out


__all__ = ["DomainHit", "DOMAINS", "detect", "detect_detailed", "domains_to_presets"]
