"""
Dialect normalizer — normalizes dialect, slang, formal, English, and
mixed language in the user's request.

The :class:`DialectNormalizer` is responsible for normalizing the
language style of the user's request.  It converts colloquial Arabic
and slang to their formal equivalents, ensuring that the same request
written in different dialects is understood the same way.

The normalizer uses the built-in dialect map (from the
:class:`LanguageRules`) as the primary normalization source, and
merges any dialect mappings from the knowledge base.

The normalizer also detects the language (Arabic, English, mixed)
and the style (formal, colloquial, slang, mixed) of the request.

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .language_rules import (
    detect_language,
    detect_style,
    normalize_arabic_text,
)
from .report_data import (
    LANGUAGE_ARABIC,
    LANGUAGE_ENGLISH,
    LANGUAGE_MIXED,
    SOURCE_LANGUAGE_RULES,
    STYLE_FORMAL,
)


class DialectNormalizer:
    """Normalizes dialect, slang, formal, English, and mixed language.

    The normalizer converts colloquial Arabic and slang to their
    formal equivalents using the dialect map.  It also normalizes
    Arabic text (removes diacritics, unifies alef variants) to ensure
    consistent matching.

    The normalizer detects the language and style of the request and
    returns both the normalized text and the detected language/style.
    """

    def normalize(
        self,
        text: str,
        dialect_map: Dict[str, str],
    ) -> Tuple[str, str, str]:
        """Normalize the dialect / style of a text.

        Parameters:
            text: The text to normalize.
            dialect_map: The dialect mapping (from the
                :class:`LanguageRules`).

        Returns:
            A tuple ``(normalized_text, language, style)`` where:
            * ``normalized_text`` is the text after dialect
              normalization.
            * ``language`` is the detected language (one of the
              ``LANGUAGE_*`` constants).
            * ``style`` is the detected style (one of the
              ``STYLE_*`` constants).
        """
        if not text:
            return "", LANGUAGE_ENGLISH, STYLE_FORMAL

        # Detect language and style on the original text.
        language = detect_language(text)
        style = detect_style(text, language, dialect_map)

        # Normalize Arabic text (remove diacritics, unify alef).
        normalized = normalize_arabic_text(text)

        # Apply dialect normalization (colloquial → formal).
        normalized = self._apply_dialect_map(normalized, dialect_map)

        return normalized, language, style

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    @staticmethod
    def _apply_dialect_map(text: str, dialect_map: Dict[str, str]) -> str:
        """Apply the dialect map to a text.

        This replaces colloquial words with their formal equivalents.
        The replacement is word-by-word to avoid partial matches.
        """
        if not dialect_map or not text:
            return text

        words = text.split()
        result: List[str] = []
        for word in words:
            if word in dialect_map:
                result.append(dialect_map[word])
            else:
                result.append(word)
        return " ".join(result)

    @staticmethod
    def detect_language_and_style(
        text: str,
        dialect_map: Dict[str, str],
    ) -> Tuple[str, str]:
        """Detect the language and style of a text.

        Returns a tuple ``(language, style)``.
        """
        if not text:
            return LANGUAGE_ENGLISH, STYLE_FORMAL

        language = detect_language(text)
        style = detect_style(text, language, dialect_map)
        return language, style


__all__ = ["DialectNormalizer"]
