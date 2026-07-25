"""
Language rules — the built-in language rules for the Semantic
Understanding Engine.

The :class:`LanguageRules` class provides the built-in knowledge that
the engine uses to understand Arabic, English, slang, formal,
abbreviations, spelling mistakes, and mixed languages.

This is the fifth data source.  Unlike the other four data sources,
the language rules are *built-in* — they do not come from the
generation context.  They are always available.

The rules include:
* **Synonyms** — mappings of different words to the same canonical
  form.  For example, "bot" and "robot" map to "bot".
* **Abbreviations** — mappings of abbreviations to their expanded
  forms.  For example, "db" expands to "database".
* **Dialect mappings** — mappings of colloquial Arabic / slang to
  their formal equivalents.
* **Spelling corrections** — common spelling mistakes mapped to
  their correct forms.
* **Intent keywords** — keywords that indicate the kind of intent
  (create, modify, delete, query, configure, deploy).
* **Stop words** — words that carry no meaning and are removed
  during analysis.

The language rules are designed to be extensible.  The
:class:`LanguageRules` class loads the built-in rules and merges any
rules provided by the knowledge base.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Dict, List, Set

from .report_data import (
    INTENT_KIND_CONFIGURE,
    INTENT_KIND_CREATE,
    INTENT_KIND_DELETE,
    INTENT_KIND_DEPLOY,
    INTENT_KIND_MODIFY,
    INTENT_KIND_QUERY,
    LANGUAGE_ARABIC,
    LANGUAGE_ENGLISH,
    LANGUAGE_MIXED,
    SOURCE_LANGUAGE_RULES,
    STYLE_COLLOQUIAL,
    STYLE_FORMAL,
    STYLE_MIXED,
    STYLE_SLANG,
)


# ---------------------------------------------------------------------------#
# Intent keywords
# ---------------------------------------------------------------------------#

INTENT_KEYWORDS: Dict[str, List[str]] = {
    INTENT_KIND_CREATE: [
        # English
        "create", "build", "make", "generate", "develop", "setup",
        "set up", "set-up", "construct", "establish", "start",
        "init", "initialize", "produce", "design", "implement",
        # Arabic (formal)
        "أنشئ", "أنشئي", "أنشئوا", "إنشاء", "بناء", "بناءً", "اصنع",
        "اصنعي", "اصنعوا", "صنع", "تطوير", "تطويري", "تطبيقا", "تصميم",
        "تأسيس", "بدء", "ابدأ", "ابدأي", "ابدأوا", "إعداد", "جهز",
        "جهزي", "جهزوا", "تكوين", "كون", "كوّن",
        # Arabic (colloquial)
        "اعمل", "اعملي", "اعملوا", "عمل", "دير", "ديروا", "ديري",
        "سوّي", "سوي", "سووا",
    ],
    INTENT_KIND_MODIFY: [
        # English
        "modify", "change", "update", "edit", "adjust", "alter",
        "refactor", "revise", "transform", "tweak", "fix", "patch",
        "upgrade", "improve", "enhance", "extend", "add", "insert",
        # Arabic (formal)
        "عدل", "عدّل", "عدّلي", "عدّلوا", "تعديل", "تغيير", "غيّر",
        "غيّري", "غيّروا", "تحديث", "حدّث", "حدّثي", "حدّثوا",
        "تحرير", "حرّر", "حرّري", "حرّروا", "إضافة", "أضف", "أضفي",
        "أضفوا", "أدخل", "أدخلي", "أدخلوا", "تحسين", "حسّن",
        "تطوير", "وسّع", "وسّعي", "وسّعوا", "توسيع",
        # Arabic (colloquial)
        "غير", "غّير", "غيري", "غيروا", "بدل", "بدّل", "بدلي",
        "بدلوا", "زود", "زيّد", "زودي", "زيدوا", "ضيف", "ضّيف",
        "ضيّفي", "ضيّفوا",
    ],
    INTENT_KIND_DELETE: [
        # English
        "delete", "remove", "drop", "erase", "clear", "purge",
        "eliminate", "destroy", "clean", "wipe", "cancel",
        # Arabic (formal)
        "حذف", "احذف", "احذفي", "احذفوا", "إزالة", "أزل", "أزلي",
        "أزلوا", "مسح", "امسح", "امسحي", "امسحوا", "إلغاء", "ألغ",
        "ألغي", "ألغوا", "تدمير", "دمّر", "دمّري", "دمّروا",
        # Arabic (colloquial)
        "امسح", "مسّح", "شيل", "شّيل", "شيّلي", "شيّلوا", "طير",
        "طيّر", "طيّري", "طيّروا",
    ],
    INTENT_KIND_QUERY: [
        # English
        "query", "search", "find", "get", "fetch", "retrieve",
        "lookup", "look up", "list", "show", "display", "view",
        "read", "check", "inspect", "ask",
        # Arabic (formal)
        "بحث", "ابحث", "ابحثي", "ابحثوا", "استعلام", "استعلم",
        "استعلمي", "استعلموا", "إيجاد", "أوجد", "استخراج", "استخرج",
        "عرض", "اعرض", "اعرضي", "اعرضوا", "إظهار", "اظهر", "اظهري",
        "اظهروا", "قراءة", "اقرأ", "اقرئي", "اقرأوا", "فحص", "افحص",
        "افحصي", "افحصوا", "سؤال", "اسأل", "اسألي", "اسألوا",
        # Arabic (colloquial)
        "دور", "دّور", "دوري", "دوروا", "شوف", "شّوف", "شوفي",
        "شوفوا", "طالع", "طالعي", "طالعوا",
    ],
    INTENT_KIND_CONFIGURE: [
        # English
        "configure", "config", "setup", "set up", "set-up",
        "settings", "options", "preferences", "customize", "customise",
        "tune", "calibrate", "wire", "connect",
        # Arabic (formal)
        "تكوين", "كوّن", "كوّني", "كوّنوا", "إعداد", "جهز", "جهّز",
        "جهّزي", "جهّزوا", "تخصيص", "خصّص", "خصّصي", "خصّصوا",
        "ضبط", "اضبط", "اضبطي", "اضبطوا", "ربط", "اربط", "اربطي",
        "اربطوا", "توصيل", "وصّل", "وصّلي", "وصّلوا",
        # Arabic (colloquial)
        "ضبط", "ضّبط", "ضبّط", "ظبط", "ظّبط", "ربط", "ربّط",
    ],
    INTENT_KIND_DEPLOY: [
        # English
        "deploy", "publish", "release", "launch", "ship", "host",
        "run", "execute", "serve", "rollout", "roll out",
        # Arabic (formal)
        "نشر", "انشر", "انشري", "انشروا", "إطلاق", "أطلق", "أطلقي",
        "أطلقوا", "تشغيل", "شغّل", "شغّلي", "شغّلوا", "تنفيذ", "نفّذ",
        "نفّذي", "نفّذوا", "استضافة", "استضيف",
        # Arabic (colloquial)
        "نزّل", "نزل", "نزلي", "نزلوا", "شغّل", "شغل", "شغلي",
        "شغلوا", "ركّب", "ركب", "ركبي", "ركبوا",
    ],
}


# ---------------------------------------------------------------------------#
# Synonyms (word → canonical form)
# ---------------------------------------------------------------------------#

BUILTIN_SYNONYMS: Dict[str, str] = {
    # English
    "bot": "bot",
    "robot": "bot",
    "chatbot": "bot",
    "chat-bot": "bot",
    "telegram": "telegram",
    "tg": "telegram",
    "tele": "telegram",
    "bot_bot": "bot",
    "store": "store",
    "shop": "store",
    "ecommerce": "store",
    "e-commerce": "store",
    "e_commerce": "store",
    "shop_bot": "store_bot",
    "storebot": "store_bot",
    "shopping": "store",
    "marketplace": "store",
    "database": "database",
    "db": "database",
    "data_base": "database",
    "sqlite": "sqlite",
    "sqlite3": "sqlite",
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "psql": "postgresql",
    "mysql": "mysql",
    "mongodb": "mongodb",
    "mongo": "mongodb",
    "redis": "redis",
    "website": "website",
    "web_site": "website",
    "webpage": "website",
    "web_page": "website",
    "site": "website",
    "app": "app",
    "application": "app",
    "feature": "feature",
    "functionality": "feature",
    "capability": "feature",
    "command": "command",
    "cmd": "command",
    "menu": "menu",
    "button": "button",
    "user": "user",
    "users": "user",
    "admin": "admin",
    "administrator": "admin",
    "message": "message",
    "msg": "message",
    "notification": "notification",
    "notify": "notification",
    "alert": "notification",
    "payment": "payment",
    "pay": "payment",
    "checkout": "payment",
    "order": "order",
    "product": "product",
    "item": "product",
    "cart": "cart",
    "basket": "cart",
    "inventory": "inventory",
    "stock": "inventory",
    "ai": "ai",
    "artificial_intelligence": "ai",
    "machine_learning": "ml",
    "ml": "ml",
    "nlp": "nlp",
    "api": "api",
    "endpoint": "api",
    "webhook": "webhook",
    "web_hook": "webhook",
    "callback": "callback",
    "call_back": "callback",
    "queue": "queue",
    "task": "task",
    "job": "task",
    "worker": "worker",
    "background": "background",
    "async": "async",
    "asynchronous": "async",
    "sync": "sync",
    "synchronous": "sync",
    # Arabic
    "بوت": "bot",
    "روبوت": "bot",
    "تيليجرام": "telegram",
    "تيليجرام": "telegram",
    "تليجرام": "telegram",
    "تلكرام": "telegram",
    "تيليقرام": "telegram",
    "متجر": "store",
    "متجر_إلكتروني": "store",
    "متجر_الكتروني": "store",
    "تجر": "store",
    "دكان": "store",
    "محل": "store",
    "قاعدة_بيانات": "database",
    "قاعده_بيانات": "database",
    "قاعدة_البيانات": "database",
    "داتا": "database",
    "بيانات": "database",
    "ميزة": "feature",
    "ميزات": "feature",
    "خاصية": "feature",
    "خصائص": "feature",
    "وظيفة": "feature",
    "أمر": "command",
    "امر": "command",
    "أوامر": "command",
    "اوامر": "command",
    "قائمة": "menu",
    "قائمه": "menu",
    "منيو": "menu",
    "زر": "button",
    "مستخدم": "user",
    "مستخدمين": "user",
    "مستخدمات": "user",
    "مستعمل": "user",
    "أدمن": "admin",
    "ادمن": "admin",
    "مدير": "admin",
    "رسالة": "message",
    "رساله": "message",
    "رسائل": "message",
    "إشعار": "notification",
    "اشعار": "notification",
    "تنبيه": "notification",
    "دفع": "payment",
    "مدفوعات": "payment",
    "طلب": "order",
    "طلبات": "order",
    "منتج": "product",
    "منتجات": "product",
    "سلعة": "product",
    "سله": "cart",
    "سلة": "cart",
    "مخزون": "inventory",
    "مخزونات": "inventory",
    "ذكاء_اصطناعي": "ai",
    "ذكاء_صناعي": "ai",
    "واجهة_برمجة": "api",
    "واجهه_برمجه": "api",
    "ويب_هوك": "webhook",
    "ويب_هوك_": "webhook",
    "طابور": "queue",
    "مهمة": "task",
    "مهام": "task",
    "عملية": "task",
    "عامل": "worker",
    "خلفية": "background",
    "تزامن": "sync",
    "غير_تزامن": "async",
}


# ---------------------------------------------------------------------------#
# Abbreviations (abbreviation → expanded form)
# ---------------------------------------------------------------------------#

BUILTIN_ABBREVIATIONS: Dict[str, str] = {
    # English
    "db": "database",
    "api": "application programming interface",
    "ui": "user interface",
    "ux": "user experience",
    "gui": "graphical user interface",
    "cli": "command line interface",
    "sdk": "software development kit",
    "cms": "content management system",
    "crm": "customer relationship management",
    "auth": "authentication",
    "authn": "authentication",
    "authz": "authorization",
    "crud": "create read update delete",
    "jwt": "json web token",
    "url": "uniform resource locator",
    "uri": "uniform resource identifier",
    "http": "hypertext transfer protocol",
    "https": "secure hypertext transfer protocol",
    "ssl": "secure sockets layer",
    "tls": "transport layer security",
    "cdn": "content delivery network",
    "dns": "domain name system",
    "ip": "internet protocol",
    "ssh": "secure shell",
    "vm": "virtual machine",
    "os": "operating system",
    "ml": "machine learning",
    "nlp": "natural language processing",
    "ai": "artificial intelligence",
    "ci": "continuous integration",
    "cd": "continuous deployment",
    "qa": "quality assurance",
    "ui_ux": "user interface and experience",
    "tg": "telegram",
    "msg": "message",
    "req": "request",
    "res": "response",
    "tmp": "temporary",
    "temp": "temporary",
    "cfg": "configuration",
    "init": "initialize",
    "img": "image",
    "btn": "button",
    "pkg": "package",
    "lib": "library",
    "repo": "repository",
    "stat": "statistics",
    "stats": "statistics",
    "sync": "synchronize",
    "async": "asynchronous",
    "num": "number",
    "qty": "quantity",
    "desc": "description",
    "info": "information",
    "doc": "document",
    "docs": "documents",
    "dir": "directory",
    "fs": "file system",
    "env": "environment",
    "var": "variable",
    "func": "function",
    "def": "definition",
    "val": "value",
    "obj": "object",
    "arr": "array",
    "str": "string",
    "len": "length",
    "min": "minimum",
    "max": "maximum",
    "avg": "average",
    "sum": "summary",
    "exec": "execute",
    "sys": "system",
    "log": "log",
    "err": "error",
    "fail": "failure",
    "ok": "okay",
    "todo": "to do",
    "fixme": "fix me",
    "wip": "work in progress",
    "ftr": "feature",
    "auth_service": "authentication service",
    # Arabic abbreviations (less common but some exist)
    "ق_ب": "قاعدة بيانات",
    "و_ب": "واجهة برمجة",
}


# ---------------------------------------------------------------------------#
# Dialect / slang mappings (colloquial → formal)
# ---------------------------------------------------------------------------#

BUILTIN_DIALECT_MAP: Dict[str, str] = {
    # Arabic colloquial → formal
    "اعمل": "أنشئ",
    "اعملي": "أنشئي",
    "اعملوا": "أنشئوا",
    "دير": "أنشئ",
    "ديري": "أنشئي",
    "ديروا": "أنشئوا",
    "سوّي": "أنشئ",
    "سوّيي": "أنشئي",
    "سوّوا": "أنشئوا",
    "سوي": "أنشئ",
    "غير": "عدّل",
    "غّير": "عدّل",
    "غيري": "عدّلي",
    "غيروا": "عدّلوا",
    "بدل": "عدّل",
    "بدّل": "عدّل",
    "بدلي": "عدّلي",
    "بدلوا": "عدّلوا",
    "زود": "أضف",
    "زيّد": "أضف",
    "زودي": "أضفي",
    "زيدوا": "أضفوا",
    "ضيف": "أضف",
    "ضّيف": "أضف",
    "ضيّف": "أضف",
    "ضيّفي": "أضفي",
    "ضيّفوا": "أضفوا",
    "شيل": "احذف",
    "شّيل": "احذف",
    "شيّلي": "احذفي",
    "شيّلوا": "احذفوا",
    "طير": "احذف",
    "طيّر": "احذف",
    "طيّري": "احذفي",
    "طيّروا": "احذفوا",
    "دور": "ابحث",
    "دّور": "ابحث",
    "دوري": "ابحثي",
    "دوروا": "ابحثوا",
    "شوف": "اعرض",
    "شّوف": "اعرض",
    "شوفي": "اعرضي",
    "شوفوا": "اعرضوا",
    "طالع": "اعرض",
    "طالعي": "اعرضي",
    "طالعوا": "اعرضوا",
    "ضبط": "اضبط",
    "ضّبط": "اضبط",
    "ضبّط": "اضبط",
    "ظبط": "اضبط",
    "ظّبط": "اضبط",
    "ربّط": "اربط",
    "نزّل": "انشر",
    "نزل": "انشر",
    "نزلي": "انشري",
    "نزلوا": "انشروا",
    "شغّل": "شغّل",
    "شغل": "شغّل",
    "شغلي": "شغّلي",
    "شغلوا": "شغّلوا",
    "ركّب": "انشر",
    "ركب": "انشر",
    "ركبي": "انشري",
    "ركبوا": "انشروا",
    "كذا": "هذا",
    "كيك": "كيف",
    "ليش": "لماذا",
    "وش": "ما",
    "وشو": "ماذا",
    "شنو": "ماذا",
    "شلون": "كيف",
    "كم_سعر": "كم_السعر",
}


# ---------------------------------------------------------------------------#
# Common spelling corrections (misspelled → correct)
# ---------------------------------------------------------------------------#

BUILTIN_SPELLING_CORRECTIONS: Dict[str, str] = {
    # English
    "recieve": "receive",
    "recieved": "received",
    "occured": "occurred",
    "occurence": "occurrence",
    "seperate": "separate",
    "seperated": "separated",
    "definately": "definitely",
    "definatly": "definitely",
    "neccessary": "necessary",
    "neccesary": "necessary",
    "accross": "across",
    "wich": "which",
    "thru": "through",
    "altho": "although",
    "thier": "their",
    "realy": "really",
    "truly": "truly",
    "trueley": "truly",
    "botton": "button",
    "buton": "button",
    "botun": "button",
    "comand": "command",
    "commad": "command",
    "comand": "command",
    "databse": "database",
    "databae": "database",
    "dataabase": "database",
    "aplication": "application",
    "apliction": "application",
    "aplication": "application",
    "teh": "the",
    "adn": "and",
    "nad": "and",
    "taht": "that",
    "thta": "that",
    "htat": "that",
    "fro": "for",
    "fron": "from",
    "form": "from",
    "wiht": "with",
    "whit": "with",
    "whcih": "which",
    "whitch": "which",
    "whic": "which",
    "telegrm": "telegram",
    "telegran": "telegram",
    "telgram": "telegram",
    "telergam": "telegram",
    "telegam": "telegram",
    "feautre": "feature",
    "feture": "feature",
    "featuer": "feature",
    "featur": "feature",
    "functon": "function",
    "fuction": "function",
    "funciton": "function",
    "funtion": "function",
    "requirment": "requirement",
    "reqiurement": "requirement",
    "requiremnet": "requirement",
    "requirment": "requirement",
    "requirments": "requirements",
    "requiremnts": "requirements",
    "configration": "configuration",
    "configration": "configuration",
    "configration": "configuration",
    "configuartion": "configuration",
    "deployement": "deployment",
    "deployemnt": "deployment",
    "deplyment": "deployment",
    "notifcation": "notification",
    "notificaton": "notification",
    "notifiction": "notification",
    "payemnt": "payment",
    "paymant": "payment",
    "inventry": "inventory",
    "inventori": "inventory",
    # Arabic common typos
    "تيليجرام": "تيليجرام",
    "تليجرم": "تيليجرام",
    "تليجارم": "تيليجرام",
    "تيلجارم": "تيليجرام",
    "متجر_كهربائي": "متجر_إلكتروني",
    "متجر_الكتروني": "متجر_إلكتروني",
    "قاعده_البيانات": "قاعدة_البيانات",
    "قاعدة_بيانات": "قاعدة_البيانات",
    "قاعده_بيانات": "قاعدة_البيانات",
}


# ---------------------------------------------------------------------------#
# Stop words (words with no meaning that are removed during analysis)
# ---------------------------------------------------------------------------#

BUILTIN_STOP_WORDS: Set[str] = {
    # English
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "being", "have", "has", "had", "do", "does", "did", "will",
    "would", "could", "should", "may", "might", "must", "shall",
    "can", "of", "to", "in", "on", "at", "by", "for", "with",
    "about", "as", "into", "through", "during", "before", "after",
    "above", "below", "from", "up", "down", "out", "off", "over",
    "under", "again", "further", "then", "once", "here", "there",
    "when", "where", "why", "how", "all", "any", "both", "each",
    "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very",
    "just", "also", "but", "and", "or", "if", "else", "because",
    "until", "while", "want", "need", "like", "please", "me",
    "my", "myself", "we", "our", "ours", "ourselves", "you",
    "your", "yours", "yourself", "yourselves", "he", "him",
    "his", "himself", "she", "her", "hers", "herself", "it",
    "its", "itself", "they", "them", "their", "theirs",
    "themselves", "what", "which", "who", "whom", "this",
    "that", "these", "those", "i", "am",
    # Arabic stop words
    "في", "من", "على", "إلى", "الى", "عن", "مع", "هذا", "هذه",
    "ذلك", "تلك", "هؤلاء", "التي", "الذي", "الذين", "اللاتي",
    "الذين", "ما", "ماذا", "كيف", "متى", "أين", "اين", "لماذا",
    "هل", "قد", "كل", "بعض", "غير", "سوف", "سـ", "ال", "و", "أو",
    "او", "ثم", "لكن", "لأن", "لان", "أن", "ان", "إن", "إنّ",
    "إنه", "إنها", "لا", "نعم", "أي", "اي", "أية", "اية",
    "كذلك", "كما", "بل", "أم", "أمّا", "اما", "إمّا", "إما",
}


# ---------------------------------------------------------------------------#
# Language rules data container
# ---------------------------------------------------------------------------#

@dataclass
class LanguageRulesData:
    """The normalised view of the language rules.

    This is the fifth data source.  It is always available because the
    rules are built-in.  When the knowledge base provides additional
    synonyms, abbreviations, or dialect mappings, they are merged
    into the built-in rules.

    Attributes:
        synonyms: The merged synonym mappings.
        abbreviations: The merged abbreviation mappings.
        dialect_map: The merged dialect / slang mappings.
        spelling_corrections: The merged spelling corrections.
        intent_keywords: The intent keywords (kind → list of
            keywords).
        stop_words: The set of stop words.
        available: Whether the language rules are available (always
            True).
    """

    synonyms: Dict[str, str] = field(default_factory=dict)
    abbreviations: Dict[str, str] = field(default_factory=dict)
    dialect_map: Dict[str, str] = field(default_factory=dict)
    spelling_corrections: Dict[str, str] = field(default_factory=dict)
    intent_keywords: Dict[str, List[str]] = field(default_factory=dict)
    stop_words: Set[str] = field(default_factory=set)
    available: bool = True

    @property
    def source_artefact(self) -> str:
        return SOURCE_LANGUAGE_RULES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "synonyms": dict(self.synonyms),
            "abbreviations": dict(self.abbreviations),
            "dialect_map": dict(self.dialect_map),
            "spelling_corrections": dict(self.spelling_corrections),
            "intent_keywords": {
                k: list(v) for k, v in self.intent_keywords.items()
            },
            "stop_words": list(self.stop_words),
            "available": self.available,
        }


# ---------------------------------------------------------------------------#
# Language rules reader / loader
# ---------------------------------------------------------------------------#

class LanguageRules:
    """Loads the built-in language rules and merges any rules from
    the knowledge base.

    The :class:`LanguageRules` class is the loader for the fifth data
    source.  It loads the built-in rules and merges any rules provided
    by the knowledge base (synonyms, abbreviations, dialect mappings,
    spelling corrections).
    """

    def load(self, knowledge_data: Any = None) -> LanguageRulesData:
        """Load the language rules and return a
        :class:`LanguageRulesData`.

        Parameters:
            knowledge_data: An optional :class:`KnowledgeData` (from
                the :class:`KnowledgeReader`) or a plain dict.  When
                provided, its synonyms, abbreviations, and dialect
                mappings are merged into the built-in rules.
        """
        synonyms = dict(BUILTIN_SYNONYMS)
        abbreviations = dict(BUILTIN_ABBREVIATIONS)
        dialect_map = dict(BUILTIN_DIALECT_MAP)
        spelling_corrections = dict(BUILTIN_SPELLING_CORRECTIONS)

        # Merge from knowledge base if provided.
        if knowledge_data is not None:
            extra_synonyms = self._get_field(knowledge_data, "synonyms")
            if isinstance(extra_synonyms, dict):
                synonyms.update(extra_synonyms)

            extra_abbreviations = self._get_field(knowledge_data, "abbreviations")
            if isinstance(extra_abbreviations, dict):
                abbreviations.update(extra_abbreviations)

            extra_dialect = self._get_field(knowledge_data, "dialect_map")
            if isinstance(extra_dialect, dict):
                dialect_map.update(extra_dialect)

            extra_spelling = self._get_field(knowledge_data, "spelling_corrections")
            if isinstance(extra_spelling, dict):
                spelling_corrections.update(extra_spelling)

        return LanguageRulesData(
            synonyms=synonyms,
            abbreviations=abbreviations,
            dialect_map=dialect_map,
            spelling_corrections=spelling_corrections,
            intent_keywords=dict(INTENT_KEYWORDS),
            stop_words=set(BUILTIN_STOP_WORDS),
            available=True,
        )

    # ----------------------------------------------------------------- #
    # Static utility methods
    # ----------------------------------------------------------------- #

    @staticmethod
    def _get_field(obj: Any, name: str) -> Any:
        """Get a field from an object or dict."""
        if obj is None:
            return None
        if isinstance(obj, dict):
            return obj.get(name)
        if hasattr(obj, name):
            return getattr(obj, name)
        return None


# ---------------------------------------------------------------------------#
# Language detection helper
# ---------------------------------------------------------------------------#

# Arabic Unicode range: U+0600 to U+06FF (Arabic), U+0750 to U+077F
# (Arabic Supplement), U+FB50 to U+FDFF (Arabic Presentation Forms-A),
# U+FE70 to U+FEFF (Arabic Presentation Forms-B).
_ARABIC_RANGE = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF]"
)

# Latin / English range: basic ASCII letters.
_LATIN_RANGE = re.compile(r"[A-Za-z]")


def detect_language(text: str) -> str:
    """Detect the language of a text.

    Returns one of the ``LANGUAGE_*`` constants:
    * ``LANGUAGE_ARABIC`` — the text is primarily Arabic.
    * ``LANGUAGE_ENGLISH`` — the text is primarily English.
    * ``LANGUAGE_MIXED`` — the text contains both Arabic and English.
    """
    if not text:
        return LANGUAGE_ENGLISH

    has_arabic = bool(_ARABIC_RANGE.search(text))
    has_latin = bool(_LATIN_RANGE.search(text))

    if has_arabic and has_latin:
        return LANGUAGE_MIXED
    if has_arabic:
        return LANGUAGE_ARABIC
    return LANGUAGE_ENGLISH


def detect_style(
    text: str,
    language: str,
    dialect_map: Dict[str, str],
) -> str:
    """Detect the style of a text.

    Returns one of the ``STYLE_*`` constants:
    * ``STYLE_FORMAL`` — the text uses formal language.
    * ``STYLE_COLLOQUIAL`` — the text uses colloquial / dialect
      language.
    * ``STYLE_SLANG`` — the text uses slang.
    * ``STYLE_MIXED`` — the text mixes formal and colloquial.
    """
    if not text:
        return STYLE_FORMAL

    words = text.lower().split()

    colloquial_count = 0
    for word in words:
        if word in dialect_map:
            colloquial_count += 1

    total_words = len(words)
    if total_words == 0:
        return STYLE_FORMAL

    colloquial_ratio = colloquial_count / total_words

    if colloquial_ratio > 0.3:
        return STYLE_COLLOQUIAL
    if 0 < colloquial_ratio <= 0.3:
        return STYLE_MIXED
    return STYLE_FORMAL


def normalize_arabic_text(text: str) -> str:
    """Normalize Arabic text by removing diacritics and unifying
    characters.

    This function:
    * Removes Arabic diacritics (tashkeel).
    * Unifies alef variants (أ، إ، آ → ا).
    * Unifies teh marbuta (ة) and heh (ه) where appropriate.
    * Removes tatweel (ـ).
    """
    if not text:
        return text

    # Remove diacritics (tashkeel).
    result = re.sub(r"[\u0617-\u061A\u064B-\u0652\u0670\u0640]", "", text)

    # Unify alef variants.
    result = result.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    result = result.replace("ٱ", "ا")

    # Unify ya variants.
    result = result.replace("ي", "ي").replace("ئ", "ي").replace("ى", "ي")

    # Unify teh marbuta → heh (common normalization for search).
    result = result.replace("ة", "ه")

    return result


__all__ = [
    "LanguageRules",
    "LanguageRulesData",
    "INTENT_KEYWORDS",
    "BUILTIN_SYNONYMS",
    "BUILTIN_ABBREVIATIONS",
    "BUILTIN_DIALECT_MAP",
    "BUILTIN_SPELLING_CORRECTIONS",
    "BUILTIN_STOP_WORDS",
    "detect_language",
    "detect_style",
    "normalize_arabic_text",
]
