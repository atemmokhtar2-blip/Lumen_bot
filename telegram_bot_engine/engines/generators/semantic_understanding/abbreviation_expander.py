"""
Abbreviation expander — expands abbreviations to their full forms.

The :class:`AbbreviationExpander` is responsible for expanding
abbreviations in the user's request to their full, expanded forms.
For example, "db" expands to "database", "api" expands to
"application programming interface".

The expander uses the built-in abbreviation dictionary (from the
:class:`LanguageRules`) as the primary expansion source, and merges
any abbreviations from the knowledge base.

The expander does not modify the original text \u2014 it records the
expansions in a mapping (``expansions``) so the caller can see which
abbreviations were expanded.

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

from typing import Dict, List

from .language_rules import normalize_arabic_text


class AbbreviationExpander:
    """Expands abbreviations to their full forms.

    The expander checks each word against the abbreviation dictionary.
    When a word is found in the dictionary, it is expanded to its full
    form.  The expander records all expansions in a mapping
    (abbreviation → expanded form) so the caller can see which
    abbreviations were expanded.

    The expander handles:
    * Direct abbreviation lookup (word → expanded form).
    * Case-insensitive lookup (``"DB"`` → ``"database"``).
    * Arabic-normalized lookup.
    * Hyphen / underscore normalization.
    """

    def expand(
        self,
        words: List[str],
        abbreviations: Dict[str, str],
    ) -> Dict[str, str]:
        """Expand abbreviations in a list of words.

        Parameters:
            words: The list of words to expand.
            abbreviations: The abbreviation dictionary (from the
                :class:`LanguageRules`).

        Returns:
            A mapping of abbreviation → expanded form.  Only
            abbreviations that were expanded are included.
        """
        expansions: Dict[str, str] = {}

        if not words:
            return expansions

        for word in words:
            if not word:
                continue

            expanded = self._expand_word(word, abbreviations)
            if expanded and expanded != word:
                expansions[word] = expanded

        return expansions

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _expand_word(
        self,
        word: str,
        abbreviations: Dict[str, str],
    ) -> str:
        """Expand a single abbreviation to its full form."""
        # Direct lookup.
        if word in abbreviations:
            return abbreviations[word]

        # Case-insensitive lookup.
        lower = word.lower()
        if lower in abbreviations:
            return abbreviations[lower]

        # All uppercase lookup (common for abbreviations like "DB").
        upper = word.upper()
        if upper in abbreviations:
            return abbreviations[upper]
        if upper.lower() in abbreviations:
            return abbreviations[upper.lower()]

        # Hyphen / underscore normalization.
        normalized_sep = word.replace("-", "_").lower()
        if normalized_sep in abbreviations:
            return abbreviations[normalized_sep]

        # Without separators.
        no_sep = word.replace("-", "").replace("_", "").lower()
        if no_sep in abbreviations:
            return abbreviations[no_sep]

        # Arabic normalization.
        arabic_normalized = normalize_arabic_text(word)
        if arabic_normalized != word:
            if arabic_normalized in abbreviations:
                return abbreviations[arabic_normalized]
            if arabic_normalized.lower() in abbreviations:
                return abbreviations[arabic_normalized.lower()]

        return word

    @staticmethod
    def apply_expansions(
        text: str,
        expansions: Dict[str, str],
    ) -> str:
        """Apply expansions to a text, returning the expanded text."""
        if not expansions:
            return text

        words = text.split()
        result: List[str] = []
        for word in words:
            if word in expansions:
                result.append(expansions[word])
            else:
                result.append(word)
        return " ".join(result)


__all__ = ["AbbreviationExpander"]
