"""
Spell corrector — handles spelling mistakes in the user's request.

The :class:`SpellCorrector` is responsible for detecting and
correcting common spelling mistakes in the user's request.  It uses
the built-in spelling corrections dictionary (from the
:class:`LanguageRules`) as the primary correction source, and falls
back to a simple edit-distance heuristic for unknown misspellings.

The corrector works on a per-word basis.  It does not modify the
original text \u2014 it records the corrections in a mapping
(``corrections``) so the caller can see which words were corrected.

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

from typing import Dict, List

from .language_rules import BUILTIN_SPELLING_CORRECTIONS, normalize_arabic_text
from .report_data import SOURCE_LANGUAGE_RULES


class SpellCorrector:
    """Corrects spelling mistakes in the user's request.

    The corrector uses a two-pass approach:
    1. **Dictionary lookup** — checks each word against the built-in
       spelling corrections dictionary.  This handles the most common
       misspellings.
    2. **Edit-distance fallback** — for unknown words, the corrector
       checks whether a known correction is within an edit distance of
       1 (a single insertion, deletion, substitution, or transposition).
       This catches typos that are not in the dictionary.

    The corrector records all corrections in a mapping (original →
    corrected) so the caller can see which words were corrected.
    """

    def __init__(self, max_candidates: int = 5) -> None:
        self._max_candidates = max_candidates

    def correct(
        self,
        words: List[str],
        spelling_corrections: Dict[str, str],
    ) -> Dict[str, str]:
        """Correct spelling mistakes in a list of words.

        Parameters:
            words: The list of words to correct.
            spelling_corrections: The spelling corrections
                dictionary (from the :class:`LanguageRules`).

        Returns:
            A mapping of original word → corrected word.  Only words
            that were corrected are included.
        """
        corrections: Dict[str, str] = {}

        if not words:
            return corrections

        # Build a set of known corrections for edit-distance lookup.
        known_corrections = set(spelling_corrections.values())
        correction_keys = set(spelling_corrections.keys())

        for word in words:
            if not word:
                continue

            # Skip words that are already in the correction values
            # (they are already correct).
            if word in known_corrections:
                continue

            # Pass 1: direct dictionary lookup.
            lower_word = word.lower()
            if lower_word in spelling_corrections:
                corrections[word] = spelling_corrections[lower_word]
                continue

            # Pass 1b: check the Arabic-normalized form.
            normalized = normalize_arabic_text(word)
            if normalized != word and normalized in spelling_corrections:
                corrections[word] = spelling_corrections[normalized]
                continue

            # Pass 2: edit-distance fallback.
            correction = self._find_closest(
                word, correction_keys, spelling_corrections,
            )
            if correction:
                corrections[word] = correction

        return corrections

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _find_closest(
        self,
        word: str,
        keys: set,
        spelling_corrections: Dict[str, str],
    ) -> str:
        """Find the closest correction within edit distance 1.

        This is a simple heuristic that checks for single-character
        insertions, deletions, substitutions, and transpositions.
        """
        if not word:
            return ""

        # Only apply edit distance for short words (longer words are
        # unlikely to be single-character typos of a known word).
        if len(word) > 15:
            return ""

        # Check transposition.
        for i in range(len(word) - 1):
            transposed = word[:i] + word[i + 1] + word[i] + word[i + 2:]
            if transposed.lower() in spelling_corrections:
                return spelling_corrections[transposed.lower()]

        # Check substitution (replace each char).
        for i in range(len(word)):
            for c in "abcdefghijklmnopqrstuvwxyz":
                substituted = word[:i] + c + word[i + 1:]
                if substituted.lower() in spelling_corrections:
                    return spelling_corrections[substituted.lower()]

        # Check deletion (remove each char).
        for i in range(len(word)):
            deleted = word[:i] + word[i + 1:]
            if deleted.lower() in spelling_corrections:
                return spelling_corrections[deleted.lower()]

        # Check insertion (insert each char at each position).
        for i in range(len(word) + 1):
            for c in "abcdefghijklmnopqrstuvwxyz":
                inserted = word[:i] + c + word[i:]
                if inserted.lower() in spelling_corrections:
                    return spelling_corrections[inserted.lower()]

        return ""

    @staticmethod
    def apply_corrections(
        text: str,
        corrections: Dict[str, str],
    ) -> str:
        """Apply corrections to a text, returning the corrected text.

        This replaces each corrected word in the text with its
        corrected form.
        """
        if not corrections:
            return text

        words = text.split()
        result: List[str] = []
        for word in words:
            if word in corrections:
                result.append(corrections[word])
            else:
                result.append(word)
        return " ".join(result)


__all__ = ["SpellCorrector"]
