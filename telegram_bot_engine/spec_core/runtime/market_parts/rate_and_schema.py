def _rate_allow(key: str, min_interval_sec: float = 0.4) -> bool:
    """Return False if the same key hit too recently."""
    now = time.monotonic()
    with _RATE_LOCK:
        last = _RATE.get(key, 0.0)
        if now - last < min_interval_sec:
            return False
        _RATE[key] = now
        # opportunistic prune
        if len(_RATE) > 5000:
            cutoff = now - 60
            for k in [k for k, t in _RATE.items() if t < cutoff]:
                _RATE.pop(k, None)
        return True


def ensure() -> None:
    init_db()


