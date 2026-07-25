"""
Sentence analyzer — performs full sentence analysis on the user's
request.

The :class:`SentenceAnalyzer` is responsible for analysing each
sentence in the user's request.  It splits the request into
sentences, detects the language and style of each sentence, extracts
keywords, resolves synonyms, corrects spelling, and expands
abbreviations.

The analyzer produces a list of :class:`SentenceAnalysis` objects,
one per sentence in the request.  Each analysis records the raw text,
the normalized text, the language, the style, the keywords, the
resolved synonyms, the spelling corrections, and the expanded
abbreviations.

This module is a pure processing component: it has no side effects and
does not modify the generation context.
"""

from __future__ import annotations

import re
from typing import Dict, List

from .abbreviation_expander import AbbreviationExpander
from .dialect_normalizer import DialectNormalizer
from .report_data import (
    LANGUAGE_ENGLISH,
    SEVERITY_INFO,
    SOURCE_LANGUAGE_RULES,
    SOURCE_USER_REQUEST,
    SentenceAnalysis,
)
from .spell_corrector import SpellCorrector
from .synonym_resolver import SynonymResolver


# Sentence splitting patterns.
# We split on periods, exclamation marks, question marks, and
# Arabic sentence terminators (؟ is the Arabic question mark).
_SENTENCE_SPLIT_RE = re.compile(r"[.!?؟\n]+")

# Arabic conjunction that often starts a new sentence.
_ARABIC_CONJUNCTIONS = {"و", "ثم", "أو", "او", "لكن", "لأن", "لان"}


class SentenceAnalyzer:
    """Analyses each sentence in the user's request.

    The analyzer:
    1. Splits the request into sentences.
    2. For each sentence:
       a. Detects the language (Arabic, English, mixed).
       b. Detects the style (formal, colloquial, slang, mixed).
       c. Corrects spelling mistakes.
       d. Expands abbreviations.
       e. Resolves synonyms.
       f. Extracts keywords (after stop-word removal).
       g. Computes a confidence score.
    3. Returns a list of :class:`SentenceAnalysis` objects.

    The analyzer is the heart of the language-processing pipeline.  It
    transforms the raw, possibly messy request into a list of clean,
    analyzed, normalized sentence analyses.
    """

    def __init__(self) -> None:
        self._spell_corrector = SpellCorrector()
        self._synonym_resolver = SynonymResolver()
        self._abbreviation_expander = AbbreviationExpander()
        self._dialect_normalizer = DialectNormalizer()

    def analyze(
        self,
        text: str,
        synonyms: Dict[str, str],
        abbreviations: Dict[str, str],
        dialect_map: Dict[str, str],
        spelling_corrections: Dict[str, str],
        stop_words: set,
    ) -> List[SentenceAnalysis]:
        """Analyse each sentence in the text.

        Parameters:
            text: The text to analyse.
            synonyms: The synonym dictionary.
            abbreviations: The abbreviation dictionary.
            dialect_map: The dialect mapping.
            spelling_corrections: The spelling corrections
                dictionary.
            stop_words: The set of stop words.

        Returns:
            A list of :class:`SentenceAnalysis` objects, one per
            sentence in the text.
        """
        if not text:
            return []

        # Split into sentences.
        sentences = self._split_sentences(text)

        analyses: List[SentenceAnalysis] = []
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue

            analysis = self._analyze_sentence(
                sentence,
                i,
                synonyms,
                abbreviations,
                dialect_map,
                spelling_corrections,
                stop_words,
            )
            analyses.append(analysis)

        return analyses

    # ----------------------------------------------------------------- #
    # Internal helpers
    # ----------------------------------------------------------------- #

    def _split_sentences(self, text: str) -> List[str]:
        """Split text into sentences.

        Splits on periods, exclamation marks, question marks,
        newlines, and the Arabic question mark (؟).
        """
        parts = _SENTENCE_SPLIT_RE.split(text)
        return [p.strip() for p in parts if p.strip()]

    def _analyze_sentence(
        self,
        sentence: str,
        index: int,
        synonyms: Dict[str, str],
        abbreviations: Dict[str, str],
        dialect_map: Dict[str, str],
        spelling_corrections: Dict[str, str],
        stop_words: set,
    ) -> SentenceAnalysis:
        """Analyse a single sentence."""
        # Detect language and style, normalize dialect.
        normalized, language, style = self._dialect_normalizer.normalize(
            sentence, dialect_map,
        )

        # Tokenize the normalized sentence.
        words = self._tokenize(normalized)

        # Correct spelling.
        spelling_results = self._spell_corrector.correct(
            words, spelling_corrections,
        )
        corrected_words = self._apply_corrections(words, spelling_results)

        # Expand abbreviations.
        abbrev_results = self._abbreviation_expander.expand(
            corrected_words, abbreviations,
        )
        expanded_words = self._apply_expansions(corrected_words, abbrev_results)

        # Resolve synonyms.
        synonym_results = self._synonym_resolver.resolve(
            expanded_words, synonyms,
        )
        resolved_words = self._apply_resolutions(expanded_words, synonym_results)

        # Extract keywords (remove stop words).
        keywords = self._extract_keywords(resolved_words, stop_words)

        # Build the normalized text from the fully processed words.
        normalized_text = " ".join(resolved_words)

        # Compute confidence.
        confidence = self._compute_confidence(
            words, spelling_results, abbrev_results, synonym_results,
        )

        return SentenceAnalysis(
            raw_text=sentence,
            normalized_text=normalized_text,
            language=language,
            style=style,
            keywords=keywords,
            resolved_synonyms=synonym_results,
            spelling_corrections=spelling_results,
            expanded_abbreviations=abbrev_results,
            confidence=confidence,
            source_artefact=SOURCE_LANGUAGE_RULES,
        )

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Tokenize a text into words.

        Splits on whitespace and punctuation (keeping Arabic and Latin
        characters).
        """
        if not text:
            return []
        # Split on whitespace and common punctuation.
        tokens = re.split(r"[\s,;:()\[\]{}'\"«»“”‘’]+", text)
        return [t.strip() for t in tokens if t.strip()]

    @staticmethod
    def _extract_keywords(words: List[str], stop_words: set) -> List[str]:
        """Extract keywords by removing stop words and deduplicating."""
        keywords: List[str] = []
        seen = set()
        for word in words:
            if not word:
                continue
            lower = word.lower()
            if lower in stop_words:
                continue
            if len(word) <= 1:
                continue
            if word in seen:
                continue
            seen.add(word)
            keywords.append(word)
        return keywords

    @staticmethod
    def _apply_corrections(
        words: List[str], corrections: Dict[str, str],
    ) -> List[str]:
        if not corrections:
            return list(words)
        return [corrections.get(w, w) for w in words]

    @staticmethod
    def _apply_expansions(
        words: List[str], expansions: Dict[str, str],
    ) -> List[str]:
        if not expansions:
            return list(words)
        return [expansions.get(w, w) for w in words]

    @staticmethod
    def _apply_resolutions(
        words: List[str], resolutions: Dict[str, str],
    ) -> List[str]:
        if not resolutions:
            return list(words)
        return [resolutions.get(w, w) for w in words]

    @staticmethod
    def _compute_confidence(
        words: List[str],
        spelling_results: Dict[str, str],
        abbrev_results: Dict[str, str],
        synonym_results: Dict[str, str],
    ) -> float:
        """Compute a confidence score for the sentence analysis.

        The confidence is high when:
        * The sentence has words (not empty).
        * Few spelling corrections were needed.
        * The sentence has keywords after processing.
        """
        if not words:
            return 0.0

        word_count = len(words)
        if word_count == 0:
            return 0.0

        # Base confidence.
        base = 1.0

        # Penalize for spelling corrections.
        spelling_penalty = len(spelling_results) / word_count * 0.1

        # Final confidence.
        confidence = base - spelling_penalty

        # Ensure it's in [0.0, 1.0].
        return max(0.0, min(1.0, confidence))


__all__ = ["SentenceAnalyzer"]
