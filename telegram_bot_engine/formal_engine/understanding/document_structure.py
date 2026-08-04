"""Document Structure Analyzer – precise sectioning for long specs."""

from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    content: str
    start_line: int = 0
    end_line: int = 0


class DocumentStructure(StrictModel):
    raw_text: str
    sections: list[Section] = Field(default_factory=list)
    title: str | None = None

    def get_section(self, *keywords: str) -> Section | None:
        kws = [k.lower() for k in keywords]
        for sec in self.sections:
            if any(k in sec.title.lower() for k in kws):
                return sec
        return None

    def section_text(self, *keywords: str) -> str:
        sec = self.get_section(*keywords)
        return sec.content if sec else ""


_HEADING_PATTERNS = [
    re.compile(r"^(?:#{1,3}\s*)?(فكرة\s*المشروع|project\s*idea|overview)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(الهدف|goal|objective)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(طريقة\s*العمل|workflow|how\s*it\s*works)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(أنواع\s*المستندات|document\s*types)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(الذكاء\s*الاصطناعي.*|ai\s*responsibilities)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(التصميم|design)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(دعم\s*اللغات|language\s*support|languages)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(جودة\s*pdf|pdf\s*quality)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(واجهة\s*تيليجرام|telegram\s*ui)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(الأداء|performance)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(الهدف\s*النهائي|final\s*goal)\s*:?\s*$", re.I),

    re.compile(r"^(?:#{1,3}\s*)?(الأوامر|commands|bot\s*commands)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(الأزرار|buttons|القائمة|menu)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(الميزات|المميزات|features)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(المتطلبات|requirements)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(قاعدة\s*البيانات|database)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(الكيانات|نماذج\s*البيانات|data\s*models|entities)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(التكامل|integrations)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(الأمان|security)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(الهدف\s*النهائي|final\s*goal)\s*:?\s*$", re.I),
    re.compile(r"^(?:#{1,3}\s*)?(وصف|description)\s*:?\s*$", re.I),

]


def _is_heading(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 90:
        return False
    if s.startswith(("-", "•", "*", "–")) or re.match(r"^\d+[\.\)]\s", s):
        return False
    for pat in _HEADING_PATTERNS:
        if pat.match(s):
            return True
    low = s.lower()
    if len(s) < 50 and not s.endswith((".", "،")):
        keys = ["فكرة", "هدف", "طريقة", "أنواع", "تصميم", "لغات", "جودة", "واجهة", "أداء",
                "idea", "goal", "design", "language", "performance"]
        if any(k in low for k in keys):
            return True
    return False


def analyze_structure(text: str) -> DocumentStructure:
    lines = text.splitlines()
    sections: list[Section] = []
    title = "preamble"
    buf: list[str] = []
    start = 0

    def flush(end: int) -> None:
        nonlocal title, buf, start
        content = "\n".join(buf).strip()
        if content:
            sections.append(Section(title=title, content=content, start_line=start, end_line=end))
        buf = []

    for i, line in enumerate(lines):
        if _is_heading(line):
            flush(i)
            title = line.strip().rstrip(":").lstrip("# ").strip()
            start = i
        else:
            buf.append(line)
    flush(len(lines))

    doc_title = None
    for line in lines[:12]:
        s = line.strip()
        if s and 5 < len(s) < 80 and not s.startswith("#"):
            doc_title = s
            break

    return DocumentStructure(raw_text=text, sections=sections, title=doc_title)
