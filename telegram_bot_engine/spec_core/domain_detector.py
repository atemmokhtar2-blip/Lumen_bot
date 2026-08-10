"""Multi-domain detector for complex free-text bot requests.

Returns domain ids that map onto existing preset / capability packs.
Scores are keyword-count based (zero-AI, deterministic).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DomainHit:
    domain: str
    score: float
    matched: tuple[str, ...]


# domain → keywords + scoring knobs
DOMAINS: dict[str, dict[str, Any]] = {
    "cybersecurity": {
        "keywords": (
            "security", "cyber", "cybersecurity", "cyberguard", "أمن", "امن", "سيبراني",
            "فحص أمني", "ثغرة", "phishing", "تصيد", "تصيّد", "dns", "tls", "ssl",
            "spf", "dmarc", "mx records", "security headers", "domain scan",
            "website scan", "soc", "incident", "vulnerability", "pentest",
            "certificate", "شهادة", "نصائح أمان", "توعية أمنية",
        ),
        "weight": 3.0,
        "min_score": 1,
        "preset": "security_ops",
    },
    "devops": {
        "keywords": (
            "docker", "kubernetes", "k8s", "ci/cd", "cicd", "deployment", "نشر",
            "حاوية", "devops", "pipeline", "helm", "terraform",
        ),
        "weight": 2.0,
        "min_score": 1,
        "preset": "saas",
    },
    "iot": {
        "keywords": (
            "iot", "أجهزة iot", "sensors", "حساسات", "mqtt", "real-time", "جهاز متصل",
        ),
        "weight": 2.0,
        "min_score": 1,
        "preset": "tasks",
    },
    "blockchain": {
        "keywords": (
            "blockchain", "بلوك تشين", "crypto", "bitcoin", "ethereum", "nft",
            "smart contract", "عقد ذكي",
        ),
        "weight": 2.2,
        "min_score": 1,
        "preset": "wallet",
    },
    "ai_ml": {
        "keywords": (
            "ai", "ml", "ذكاء اصطناعي", "تعلم آلي", "gpt", "chatgpt", "openai",
            "machine learning", "llm",
        ),
        "weight": 2.0,
        "min_score": 2,  # "ai" alone is noisy
        "preset": "notes",
    },
    "ecommerce": {
        "keywords": (
            "shop", "store", "متجر", "بيع", "products", "منتجات", "ecommerce",
            "سلة", "cart", "كتالوج", "catalog", "checkout",
        ),
        "weight": 1.8,
        "min_score": 2,
        "preset": "shop",
    },
    "healthcare": {
        "keywords": (
            "medical", "health", "طبي", "صحة", "hospital", "مستشفى", "عيادة", "clinic",
        ),
        "weight": 2.0,
        "min_score": 1,
        "preset": "clinic",
    },
    "education": {
        "keywords": (
            "education", "course", "تعليم", "دورة", "school", "مدرسة", "كورس", "quiz",
        ),
        "weight": 1.8,
        "min_score": 1,
        "preset": "education",
    },
    "finance": {
        "keywords": (
            "finance", "مالية", "accounting", "محاسبة", "ledger", "دفتر", "kyc", "aml",
        ),
        "weight": 2.0,
        "min_score": 1,
        "preset": "finance",
    },
    "logistics": {
        "keywords": (
            "logistics", "لوجستيات", "shipping", "شحن", "delivery", "توصيل",
            "warehouse", "مستودع", "fleet",
        ),
        "weight": 1.9,
        "min_score": 1,
        "preset": "logistics",
    },
    "projects": {
        "keywords": (
            "project", "projects", "مشروع", "مشاريع", "project management",
            "إدارة مشاريع",
        ),
        "weight": 1.6,
        "min_score": 1,
        "preset": "tasks",
    },
    "saas": {
        "keywords": (
            "saas", "multi-tenant", "workspace", "tenant", "rbac", "quota", "seats",
        ),
        "weight": 2.2,
        "min_score": 1,
        "preset": "saas",
    },
}


def detect(text: str, *, limit: int = 6) -> list[str]:
    """Domain ids with score ≥ min_score, strongest first."""
    return [h.domain for h in detect_detailed(text, limit=limit)]


def detect_detailed(text: str, *, limit: int = 6) -> list[DomainHit]:
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
    """Map domain ids → existing preset ids (deduped, order preserved)."""
    out: list[str] = []
    seen: set[str] = set()
    for d in domains:
        preset = (DOMAINS.get(d) or {}).get("preset")
        if preset and preset not in seen:
            seen.add(preset)
            out.append(str(preset))
    return out


__all__ = ["DomainHit", "DOMAINS", "detect", "detect_detailed", "domains_to_presets"]
