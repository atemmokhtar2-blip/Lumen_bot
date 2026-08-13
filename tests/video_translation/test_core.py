from pathlib import Path

import pytest

from video_translation_bot.engines.local_ai import IdentityTranslationEngine, LocalModelError
from video_translation_bot.engines.translation import TranslationPipeline
from video_translation_bot.models import Segment, SubtitleConfiguration, TranscriptPackage, Word


def transcript() -> TranscriptPackage:
    words = [
        Word(word_id="w1", text="I", start_time=0.0, end_time=0.2, confidence=0.95),
        Word(word_id="w2", text="want", start_time=0.2, end_time=0.5, confidence=0.95),
        Word(word_id="w3", text="to", start_time=0.5, end_time=0.6, confidence=0.95),
        Word(word_id="w4", text="go", start_time=0.6, end_time=1.0, confidence=0.95),
    ]
    return TranscriptPackage(job_id="JOB-1", source_language="en", duration=1.0, segments=[Segment(segment_id="s1", start_time=0.0, end_time=1.0, text="I want to go", confidence=0.95, words=words)], words=words, raw_transcript="I want to go", clean_transcript="I want to go")


def test_no_closed_api_fallback_fails_loudly():
    with pytest.raises(LocalModelError):
        IdentityTranslationEngine().translate("hello", "en", "ar")


def test_same_language_translation_is_deterministic():
    class SameLanguage:
        def translate(self, text, source_language, target_language, context):
            return text

    package = TranslationPipeline(SameLanguage()).build_package(transcript(), SubtitleConfiguration(target_language="en"))
    assert package.translation_package.translated_segments[0].translated_text == "I want to go"
    assert package.subtitle_timeline.subtitles[0].start_time < package.subtitle_timeline.subtitles[0].end_time
    assert package.subtitle_timeline.subtitles[0].word_mapping


def test_important_word_detection_and_quality():
    class SameLanguage:
        def translate(self, text, source_language, target_language, context):
            return text

    package = TranslationPipeline(SameLanguage()).build_package(transcript(), SubtitleConfiguration(target_language="en", highlight_enabled=True))
    subtitle = package.subtitle_timeline.subtitles[0]
    assert "go" in subtitle.highlight_words
    assert package.quality_report["status"] in {"QUALITY_GOOD", "QUALITY_WARNING"}
