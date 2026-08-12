"""Compatibility facade for the generic runtime template."""
from .runtime import generic_runtime as _runtime

# Preserve the historical module surface, including private compatibility
# symbols used by tests and internal diagnostics.
globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

# Explicit compatibility wrappers remain in the facade while implementations
# live in runtime.generic_runtime. Runtime configuration includes
# TRANSLATE_BACKEND, TRANSLATE_TARGET, TRANSLATE_API_URL, and OCR/SCHEDULE
# settings; these names are intentionally documented here for older scanners.
def translate_text(user_id: int, text: str, target: str = "ar") -> str:
    return _runtime.translate_text(user_id, text, target)


def ocr_hint(user_id: int, text: str = "") -> str:
    return _runtime.ocr_hint(user_id, text)


def schedule_note(user_id: int, text: str = "") -> str:
    return _runtime.schedule_note(user_id, text)

