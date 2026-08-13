from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from ..models import Segment, Word


class LocalModelError(RuntimeError):
    pass


class SpeechEngine(ABC):
    @abstractmethod
    def transcribe(self, audio_path: Path) -> tuple[str, float, list[Segment], list[Word], list[str]]:
        raise NotImplementedError


class FasterWhisperSpeechEngine(SpeechEngine):
    """Optional local faster-whisper backend; model files are downloaded/managed locally by the operator."""

    def __init__(self, model_size: str = "small", device: str = "cpu", compute_type: str = "int8"):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise LocalModelError("Install faster-whisper and provide a local model before enabling speech recognition.") from exc
        self.model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio_path: Path) -> tuple[str, float, list[Segment], list[Word], list[str]]:
        segments_iter, info = self.model.transcribe(str(audio_path), word_timestamps=True, vad_filter=True)
        segments: list[Segment] = []
        words: list[Word] = []
        speakers: list[str] = []
        for index, item in enumerate(segments_iter):
            segment_words: list[Word] = []
            for word_index, token in enumerate(item.words or []):
                word = Word(word_id=f"W_{index:05d}_{word_index:04d}", text=token.word.strip(), start_time=float(token.start), end_time=float(token.end), confidence=float(token.probability or 0.0))
                segment_words.append(word)
                words.append(word)
            segments.append(Segment(segment_id=f"SEG_{index:05d}", start_time=float(item.start), end_time=float(item.end), text=item.text.strip(), confidence=float(getattr(item, "avg_logprob", 0.0) and min(1.0, max(0.0, 0.5 + float(item.avg_logprob) / 4)) or 0.0), words=segment_words))
        text = " ".join(segment.text for segment in segments).strip()
        language = getattr(info, "language", "und") or "und"
        confidence = float(getattr(info, "language_probability", 0.0) or 0.0)
        return language, confidence, segments, words, speakers


class TranslationEngine(ABC):
    @abstractmethod
    def translate(self, text: str, source_language: str, target_language: str, context: dict[str, Any]) -> str:
        raise NotImplementedError


class ArgosTranslationEngine(TranslationEngine):
    """Argos Translate adapter. It only uses locally installed language packages."""

    def __init__(self):
        try:
            import argostranslate.translate as translate
        except ImportError as exc:
            raise LocalModelError("Install argostranslate and its local language package before enabling translation.") from exc
        self._translate = translate

    def translate(self, text: str, source_language: str, target_language: str, context: dict[str, Any]) -> str:
        if not text.strip() or source_language == target_language or target_language.startswith(source_language):
            return text
        try:
            return self._translate.translate(text, source_language.split("-")[0], target_language.split("-")[0])
        except Exception as exc:
            raise LocalModelError(f"No local Argos model is installed for {source_language}->{target_language}.") from exc


class IdentityTranslationEngine(TranslationEngine):
    """Deterministic safe fallback: never fabricates a translation when no local model exists."""

    def translate(self, text: str, source_language: str, target_language: str, context: dict[str, Any]) -> str:
        if source_language == target_language:
            return text
        raise LocalModelError(f"No local translation backend configured for {source_language}->{target_language}.")


class LocalKeywordImportance:
    _EMOTION = {"love", "hate", "angry", "happy", "خسارة", "حب", "غضب", "فرح"}
    _ACTION = {"go", "stop", "run", "start", "finish", "اذهب", "توقف", "ابدأ"}

    def score(self, token: str) -> tuple[float, str | None]:
        normalized = re.sub(r"[^\w\u0600-\u06ff]", "", token.lower())
        if normalized.isdigit():
            return 0.9, "NUMBER"
        if normalized in self._EMOTION:
            return 0.85, "EMOTION"
        if normalized in self._ACTION:
            return 0.75, "ACTION"
        if len(normalized) >= 9:
            return 0.55, "KEY_TERM"
        if token.isupper() and len(token) > 2:
            return 0.7, "EMPHASIS"
        return 0.1, None
