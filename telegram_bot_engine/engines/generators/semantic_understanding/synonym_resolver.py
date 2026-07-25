"""
Synonym resolver — resolves synonyms to their canonical forms.

The :class:`SynonymResolver` is responsible for mapping different
words that mean the same thing to a single, canonical form.  For
example, "bot", "robot", and "chatbot" all map to "bot".

The resolver uses the built-in synonym dictionary (from the
:class:`LanguageRules`) as the primary resolution source, and merges
any synonyms from the knowledge base.

The resolver does not modify the original text \u2014 it records the
resolutions in a mapping (``resolutions``) so the caller can see which
words were resolved.

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

from typing import Dict, List

from .language_rules import normalize_arabic_text
from .report_data import SOURCE_LANGUAGE_RULES


class SynonymResolver:
    """Resolves synonyms to their canonical forms.

    The resolver checks each word against the synonym dictionary.  When
    a word is found in the dictionary, it is resolved to its canonical
    form.  The resolver records all resolutions in a mapping
    (original → canonical) so the caller can see which words were
    resolved.

    The resolver handles:
    * Direct synonym lookup (word → canonical).
    * Case-insensitive lookup (``"Bot"`` → ``"bot"``).
    * Arabic-normalized lookup (for Arabic words with diacritics or
      alef variants).
    * Hyphen / underscore normalization (``"chat-bot"`` →
      ``"chat_bot"`` → ``"bot"``).
    """

    def resolve(
        self,
        words: List[str],
        synonyms: Dict[str, str],
    ) -> Dict[str, str]:
        """Resolve synonyms in a list of words.

        Parameters:
            words: The list of words to resolve.
            synonyms: The synonym dictionary (from the
                :class:`LanguageRules`).

        Returns:
            A mapping of original word → resolved (canonical) form.
            Only words that were resolved are included.
        """
        resolutions: Dict[str, str] = {}

        if not words:
            return resolutions

        for word in words:
            if not word:
                continue

            resolved = self._resolve_word(word, synonyms)
            if resolved and resolved != word:
                resolutions[word] = resolved

        return resolutions

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _resolve_word(
        self,
        word: str,
        synonyms: Dict[str, str],
    ) -> str:
        """Resolve a single word to its canonical form."""
        # Direct lookup.
        if word in synonyms:
            return synonyms[word]

        # Case-insensitive lookup.
        lower = word.lower()
        if lower in synonyms:
            return synonyms[lower]

        # Hyphen / underscore normalization.
        normalized_sep = word.replace("-", "_").lower()
        if normalized_sep in synonyms:
            return synonyms[normalized_sep]

        # Without separators.
        no_sep = word.replace("-", "").replace("_", "").lower()
        if no_sep in synonyms:
            return synonyms[no_sep]

        # Arabic normalization.
        arabic_normalized = normalize_arabic_text(word)
        if arabic_normalized != word:
            if arabic_normalized in synonyms:
                return synonyms[arabic_normalized]
            if arabic_normalized.lower() in synonyms:
                return synonyms[arabic_normalized.lower()]
            # With underscore join.
            joined = arabic_normalized.replace(" ", "_")
            if joined in synonyms:
                return synonyms[joined]

        return word

    @staticmethod
    def apply_resolutions(
        text: str,
        resolutions: Dict[str, str],
    ) -> str:
        """Apply resolutions to a text, returning the resolved text."""
        if not resolutions:
            return text

        words = text.split()
        result: List[str] = []
        for word in words:
            if word in resolutions:
                result.append(resolutions[word])
            else:
                result.append(word)
        return " ".join(result)


__all__ = ["SynonymResolver"]
