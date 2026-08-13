"""Fuzzy matching — pure Python with optional rapidfuzz acceleration."""
from __future__ import annotations


def _lev_ratio(a: str, b: str) -> float:
    if a == b:
        return 100.0
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    if la < lb:
        a, b, la, lb = b, a, lb, la
    # quick reject
    if la - lb > max(2, la // 3):
        return 0.0
    prev = list(range(lb + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return 100.0 * (1.0 - prev[-1] / max(la, 1))


def ratio(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz  # type: ignore

        return float(fuzz.ratio(a, b))
    except Exception:
        return _lev_ratio(a, b)


def partial_ratio(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz  # type: ignore

        return float(fuzz.partial_ratio(a, b))
    except Exception:
        if not a or not b:
            return 0.0
        if a in b or b in a:
            shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
            return 100.0 * len(shorter) / max(len(longer), 1) + 20.0
        # windowed
        if len(a) > len(b):
            a, b = b, a
        best = 0.0
        for i in range(0, len(b) - len(a) + 1):
            best = max(best, _lev_ratio(a, b[i : i + len(a)]))
        return best


def token_set_ratio(a: str, b: str) -> float:
    try:
        from rapidfuzz import fuzz  # type: ignore

        return float(fuzz.token_set_ratio(a, b))
    except Exception:
        sa, sb = set(a.split()), set(b.split())
        if not sa or not sb:
            return 0.0
        inter = len(sa & sb)
        return 100.0 * inter / max(len(sa | sb), 1)


def best_match(
    token: str,
    candidates: list[str],
    *,
    cutoff: float = 75.0,
) -> tuple[str | None, float]:
    if not token or not candidates:
        return None, 0.0
    best_s = -1.0
    best_c: str | None = None
    for c in candidates:
        s = ratio(token, c)
        if s > best_s:
            best_s, best_c = s, c
    if best_s >= cutoff:
        return best_c, best_s
    return None, best_s


def best_matches(
    token: str,
    candidates: list[str],
    *,
    cutoff: float = 75.0,
    limit: int = 3,
) -> list[tuple[str, float]]:
    scored = [(c, ratio(token, c)) for c in candidates]
    scored = [(c, s) for c, s in scored if s >= cutoff]
    scored.sort(key=lambda x: -x[1])
    return scored[:limit]


__all__ = ["ratio", "partial_ratio", "token_set_ratio", "best_match", "best_matches"]
