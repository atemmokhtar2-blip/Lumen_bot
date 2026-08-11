"""Fast pure-Python fuzzy match (optional rapidfuzz boost)."""
from __future__ import annotations


def _ratio(a: str, b: str) -> float:
    if a == b:
        return 100.0
    if not a or not b:
        return 0.0
    # try rapidfuzz
    try:
        from rapidfuzz import fuzz  # type: ignore

        return float(fuzz.ratio(a, b))
    except Exception:
        pass
    # Levenshtein distance → ratio
    la, lb = len(a), len(b)
    if la < lb:
        a, b = b, a
        la, lb = lb, la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            ins = cur[j - 1] + 1
            delete = prev[j] + 1
            sub = prev[j - 1] + (0 if ca == cb else 1)
            cur.append(min(ins, delete, sub))
        prev = cur
    dist = prev[-1]
    return 100.0 * (1.0 - dist / max(la, lb, 1))


def best_match(token: str, candidates: list[str], *, cutoff: float = 78.0) -> tuple[str | None, float]:
    """Return best candidate and score if >= cutoff."""
    if not token or not candidates:
        return None, 0.0
    best_s = -1.0
    best_c: str | None = None
    for c in candidates:
        s = _ratio(token, c)
        if s > best_s:
            best_s = s
            best_c = c
    if best_s >= cutoff:
        return best_c, best_s
    return None, best_s


def partial_ratio(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz  # type: ignore

        return float(fuzz.partial_ratio(a, b))
    except Exception:
        if a in b or b in a:
            return 90.0
        return _ratio(a, b)


__all__ = ["best_match", "partial_ratio"]
