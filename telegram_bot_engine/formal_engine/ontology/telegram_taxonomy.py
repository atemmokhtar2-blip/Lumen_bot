"""Telegram Bot Core Taxonomy – precise and extensible."""

from __future__ import annotations

from .base import ConceptKind, OntologyID, RelationType
from .concepts import Concept, ConceptRegistry, Relation


def _c(name: str, kind: ConceptKind, definition: str,
       labels: dict[str, str] | None = None,
       synonyms: list[str] | None = None,
       surface_forms: list[str] | None = None,
       properties: dict | None = None,
       tags: list[str] | None = None) -> Concept:
    return Concept(
        id=OntologyID(), kind=kind, canonical_name=name, definition=definition,
        labels=labels or {}, synonyms=synonyms or [], surface_forms=surface_forms or [],
        properties=properties or {}, tags=tags or [],
    )


def build_core_taxonomy() -> ConceptRegistry:
    concepts: list[Concept] = []

    concepts += [
        _c("document_designer", ConceptKind.BOT_CAPABILITY,
           "Professional document designer that produces print-ready PDFs.",
           labels={"ar": "مصمم مستندات"},
           surface_forms=["مصمم مستندات", "document designer", "مصمم pdf", "يعمل بالذكاء الاصطناعي"],
           tags=["core"]),
        _c("text_to_pdf", ConceptKind.BOT_CAPABILITY, "Converts text to PDF.",
           surface_forms=["تحويل إلى pdf", "text to pdf", "إنشاء pdf", "ملف pdf"], tags=["pdf"]),
        _c("auto_document_type_detection", ConceptKind.BOT_CAPABILITY,
           "Detects document type automatically without asking.",
           surface_forms=["يكتشف النوع تلقائيًا", "تلقائيًا دون سؤال", "بدون سؤال المستخدم",
                          "يحدد نوع المستند تلقائيًا", "auto detect"], tags=["intelligence"]),
        _c("content_improvement", ConceptKind.BOT_CAPABILITY,
           "Improves text quality.",
           surface_forms=["تحسين الصياغة", "تصحيح الأخطاء", "إعادة ترتيب الفقرات"], tags=["quality"]),
        _c("structural_generation", ConceptKind.BOT_CAPABILITY,
           "Generates structural elements (cover, TOC, headers...).",
           surface_forms=["غلاف", "فهرس", "عناوين فرعية", "header", "footer", "ترقيم الصفحات"],
           tags=["structure"]),
        _c("multi_language_support", ConceptKind.BOT_CAPABILITY,
           "Arabic RTL + English + mixed.",
           surface_forms=["العربية", "من اليمين إلى اليسار", "rtl", "الإنجليزية", "لغتين", "اللغتين معًا"],
           tags=["i18n"]),
        _c("progress_feedback", ConceptKind.BOT_CAPABILITY,
           "Shows progress to the user.",
           surface_forms=["حالة التنفيذ", "progress", "يعرض للمستخدم حالة"], tags=["ux"]),
        _c("concurrent_users", ConceptKind.BOT_CAPABILITY,
           "Handles many users concurrently.",
           surface_forms=["عدة مستخدمين", "في نفس الوقت", "concurrent"], tags=["performance"]),
    ]

    for name, ar, en in [
        ("report", "تقرير", "Report"), ("research", "بحث", "Research"),
        ("article", "مقال", "Article"), ("book", "كتاب", "Book"),
        ("summary", "ملخص", "Summary"), ("memo", "مذكرة", "Memo"),
        ("cv", "سيرة ذاتية", "CV"), ("invoice", "فاتورة", "Invoice"),
        ("formal_letter", "خطاب رسمي", "Formal Letter"), ("contract", "عقد", "Contract"),
        ("business_plan", "خطة عمل", "Business Plan"),
        ("project_proposal", "عرض مشروع", "Project Proposal"),
        ("general_document", "مستند عام", "General Document"),
    ]:
        concepts.append(_c(name, ConceptKind.DOCUMENT_TYPE, f"Type: {en}",
                           labels={"ar": ar, "en": en},
                           surface_forms=[ar, en.lower(), name.replace("_", " ")],
                           tags=["document_type"]))

    concepts += [
        _c("design_system_modern_clean", ConceptKind.DESIGN_TOKEN,
           "Modern clean elegant design.",
           surface_forms=["حديثة ونظيفة وأنيقة", "حديث ونظيف", "modern", "clean", "elegant"],
           tags=["design"]),
        _c("color_palette_white_blue_gray", ConceptKind.DESIGN_TOKEN,
           "White + blue + gray.",
           surface_forms=["الأبيض والأزرق", "لمسات رمادية", "أبيض وأزرق"],
           properties={"primary": ["#FFFFFF", "#1E3A8A"], "accent": "#6B7280"}, tags=["design"]),
        _c("print_ready", ConceptKind.DESIGN_TOKEN, "Print-optimized.",
           surface_forms=["جاهز للطباعة", "جاهزة للطباعة", "مناسبًا للطباعة", "للطباعة"], tags=["design"]),
        _c("embedded_fonts", ConceptKind.DESIGN_TOKEN, "Fonts embedded.",
           surface_forms=["خطوط مدمجة", "مدمجة داخل الملف"], tags=["pdf"]),
        _c("selectable_text", ConceptKind.DESIGN_TOKEN, "Selectable text.",
           surface_forms=["نص قابل للنسخ", "قابل للنسخ"], tags=["pdf"]),
        _c("postgres_database", ConceptKind.TECHNICAL_COMPONENT, "PostgreSQL.",
           surface_forms=["postgres", "postgresql", "قاعدة بيانات"], tags=["database"]),
        _c("pdf_engine", ConceptKind.TECHNICAL_COMPONENT, "PDF generation engine.",
           surface_forms=["محرك pdf", "pdf engine"], tags=["pdf"]),
        _c("async_task_queue", ConceptKind.TECHNICAL_COMPONENT, "Background queue.",
           surface_forms=["queue", "خلفية", "background"], tags=["performance"]),
        _c("state_management", ConceptKind.TECHNICAL_COMPONENT, "Conversation state.",
           surface_forms=["state", "conversation", "حالة"], tags=["core"]),
        _c("high_performance", ConceptKind.QUALITY_ATTRIBUTE, "High speed.",
           surface_forms=["سرعة عالية", "أداء عالي"], tags=["nfr"]),
        _c("full_error_handling", ConceptKind.QUALITY_ATTRIBUTE, "Full error handling.",
           surface_forms=["معالجة الأخطاء", "معالجة أخطاء"], tags=["nfr"]),
        _c("modular_extensible_code", ConceptKind.QUALITY_ATTRIBUTE, "Clean modular code.",
           surface_forms=["كود منظم", "قابل للتطوير", "منظم وقابل"], tags=["nfr"]),
        _c("high_availability", ConceptKind.QUALITY_ATTRIBUTE, "Stable.",
           surface_forms=["استقرار كامل", "استقرار"], tags=["nfr"]),
        _c("professional_welcome", ConceptKind.UI_ELEMENT, "Professional welcome.",
           surface_forms=["ترحيب احترافي", "ترحيب"], tags=["ui"]),
        _c("primary_action_button", ConceptKind.UI_ELEMENT, "Main button.",
           surface_forms=["زر", "إنشاء pdf جديد"], tags=["ui"]),
        _c("payment_gateway", ConceptKind.TECHNICAL_COMPONENT, "Payment integration.",
           surface_forms=["دفع إلكتروني", "بوابة دفع", "payment", "stripe", "myfatoorah"], tags=["finance"]),
        _c("external_api_integration", ConceptKind.TECHNICAL_COMPONENT, "External API connection.",
           surface_forms=["ربط خارجي", "api", "integration", "تكامل"], tags=["integration"]),
        _c("role_based_access", ConceptKind.BOT_CAPABILITY, "RBAC support.",
           surface_forms=["صلاحيات", "أدوار", "admin only", "مدير"], tags=["security"]),
        _c("relational_data_model", ConceptKind.TECHNICAL_COMPONENT, "One-to-many / Many-to-many support.",
           surface_forms=["علاقات بيانات", "مرتبط بـ", "relation"], tags=["database"]),
    ]

    registry = ConceptRegistry(concepts={c.canonical_name: c for c in concepts})

    def req(src: str, tgt: str) -> None:
        s, t = registry.get(src), registry.get(tgt)
        if s and t:
            registry.relations.append(  # type: ignore
                Relation(source_id=s.id, target_id=t.id, relation_type=RelationType.REQUIRES)
            )

    req("document_designer", "text_to_pdf")
    req("document_designer", "auto_document_type_detection")
    req("document_designer", "pdf_engine")
    req("document_designer", "design_system_modern_clean")
    req("document_designer", "multi_language_support")
    req("document_designer", "structural_generation")
    req("document_designer", "postgres_database")
    req("text_to_pdf", "pdf_engine")
    req("concurrent_users", "async_task_queue")
    req("concurrent_users", "postgres_database")
    req("progress_feedback", "state_management")
    req("print_ready", "embedded_fonts")
    req("print_ready", "selectable_text")

    registry.finalize()
    return registry


CORE_TAXONOMY = build_core_taxonomy()
