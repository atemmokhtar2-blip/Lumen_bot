def _norm(text: str) -> str:
    """Normalize whitespace + light Arabic orthography (no heavy NLP deps)."""
    t = (text or "").strip().lower()
    # strip Arabic diacritics
    t = re.sub(r"[\u064B-\u065F\u0670]", "", t)
    # alef variants → ا
    t = t.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا").replace("ٱ", "ا")
    # taa marbuta → ه for matching flexibility
    t = t.replace("ة", "ه")
    # alef maqsura → ي
    t = t.replace("ى", "ي")
    return re.sub(r"\s+", " ", t)


def _has_any(text: str, keys: Iterable[str]) -> bool:
    t = _norm(text)
    return any(k in t for k in keys)



def _token_hit(t: str, k: str) -> bool:
    k = (k or "").strip().lower()
    if not k or k not in t:
        return False
    if len(k) <= 3:
        idx = 0
        while True:
            i = t.find(k, idx)
            if i < 0:
                return False
            before = t[i - 1] if i > 0 else " "
            after = t[i + len(k)] if i + len(k) < len(t) else " "
            def _wc(ch: str) -> bool:
                return ch.isalnum() or ("؀" <= ch <= "ۿ")
            if not _wc(before) and not _wc(after):
                return True
            idx = i + 1
        return False
    return True


def _score_keys(text: str, keys: Iterable[str], weight: float = 1.0) -> float:
    """Longest-phrase-first scoring with span neutralization.

    Longer explicit phrases (e.g. «موعد المهمة», «حجز موعد») outrank short
    shared tokens so booking cannot steal a pure tasks request.
    """
    t = _norm(text)
    ordered = sorted({(k or "").strip().lower() for k in keys if k}, key=len, reverse=True)
    matched: list[str] = []
    mask = t
    for k in ordered:
        if not k:
            continue
        if len(k) <= 3:
            if not _token_hit(mask, k):
                continue
        elif k not in mask:
            continue
        matched.append(k)
        mask = mask.replace(k, " " * len(k), 1)
    if not matched:
        return 0.0
    phrase_bonus = sum(min(len(k), 32) * 0.08 for k in matched)
    return len(matched) * float(weight) + phrase_bonus



# Presets that cannot coexist when a family has a clear winner.
_EXCLUSIVE_FAMILIES: tuple[frozenset[str], ...] = (
    frozenset({"tasks", "booking", "clinic"}),
    frozenset({"shop", "commerce_pro", "marketplace", "clinic", "booking"}),
    frozenset({"tasks", "shop", "commerce_pro", "restaurant"}),
)

_MEDICAL_ANCHORS = (
    "عياده", "عيادة", "clinic", "دكتور", "طبيب", "مريض", "hospital", "مستشفي",
    "مستشفى", "موعد طبي", "وصفه", "وصفة", "صيدليه", "صيدلية", "patient", "doctor",
)
_BOOKING_ANCHORS = (
    "حجز", "booking", "احجز", "صالون", "حلاق", "salon", "باربر", "تجميل",
)
_TASK_ANCHORS = (
    "مهام", "مهمه", "مهمة", "todo", "task", "tasks", "قائمه مهام", "قائمة مهام",
    "حذف مهمه", "حذف مهمة", "اضافه مهمه", "اضافة مهمة", "إضافة مهمة",
)


