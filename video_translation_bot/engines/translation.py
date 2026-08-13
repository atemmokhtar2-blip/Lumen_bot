from __future__ import annotations

import re
from typing import Any

from ..models import Segment, Subtitle, SubtitleConfiguration, SubtitlePackage, SubtitleTimeline, TranscriptPackage, TranslationPackage, TranslatedSegment, TranslationMode, WordMapping
from .local_ai import LocalKeywordImportance, LocalModelError, TranslationEngine


class TranslationPipeline:
    def __init__(self, engine: TranslationEngine, *, importance: LocalKeywordImportance | None = None):
        self.engine = engine
        self.importance = importance or LocalKeywordImportance()

    def build_package(self, transcript: TranscriptPackage, config: SubtitleConfiguration) -> SubtitlePackage:
        context: dict[str, Any] = {"previous": "", "terminology_map": {}, "speaker_style": {}}
        translated: list[TranslatedSegment] = []
        for index, segment in enumerate(transcript.segments):
            previous = transcript.segments[index - 1].text if index else ""
            following = transcript.segments[index + 1].text if index + 1 < len(transcript.segments) else ""
            context.update({"previous": previous, "next": following, "speaker": segment.speaker_id, "source_language": transcript.source_language, "target_language": config.target_language, "mode": config.translation_mode.value})
            translated_text = self.engine.translate(segment.text, transcript.source_language, config.target_language, context)
            mappings = self._map_words(segment, translated_text)
            translated.append(TranslatedSegment(segment_id=segment.segment_id, source_text=segment.text, translated_text=translated_text, start_time=segment.start_time, end_time=segment.end_time, speaker_id=segment.speaker_id, word_mapping=mappings))
        translation = TranslationPackage(job_id=transcript.job_id, source_language=transcript.source_language, target_language=config.target_language, translation_mode=config.translation_mode, translated_segments=translated, terminology_map=context.get("terminology_map", {}), translation_quality=self._translation_quality(translated), context_metadata={"content_type": self._classify(transcript), "speaker_count": len(transcript.speakers)})
        subtitles = self._segment_subtitles(translation, transcript, config)
        timeline = SubtitleTimeline(job_id=transcript.job_id, target_language=config.target_language, mode=config.subtitle_mode, subtitles=subtitles, duration=transcript.duration, quality_score=self._timeline_quality(subtitles, config))
        return SubtitlePackage(job_id=transcript.job_id, source_language=transcript.source_language, target_language=config.target_language, subtitle_timeline=timeline, translation_package=translation, caption_metadata={"caption_density": config.caption_density, "karaoke_enabled": config.karaoke_enabled}, quality_report=self._quality_report(subtitles, translation))

    def _classify(self, transcript: TranscriptPackage) -> list[str]:
        text = transcript.clean_transcript.lower()
        classes = ["DIALOGUE"]
        if len(transcript.segments) > 20 and any(token in text for token in ("subscribe", "follow", "اشترك")):
            classes.append("SOCIAL_MEDIA")
        if "\n" in transcript.raw_transcript or "chorus" in text:
            classes.append("LYRICS")
        return classes

    def _map_words(self, segment: Segment, translated: str) -> list[WordMapping]:
        target_tokens = translated.split()
        if not target_tokens:
            return []
        source_words = segment.words or []
        result: list[WordMapping] = []
        for index, token in enumerate(target_tokens):
            if source_words:
                left = round(index * len(source_words) / len(target_tokens))
                right = max(left + 1, round((index + 1) * len(source_words) / len(target_tokens)))
                selected = source_words[min(left, len(source_words)-1):min(right, len(source_words))]
                start, end = selected[0].start_time, selected[-1].end_time
                ids = [item.word_id for item in selected]
            else:
                span = max(0.01, segment.end_time - segment.start_time) / len(target_tokens)
                start, end = segment.start_time + index * span, segment.start_time + (index + 1) * span
                ids = []
            score, kind = self.importance.score(token)
            result.append(WordMapping(source_word_ids=ids, target_text=token, start_time=start, end_time=end, importance_score=score, importance_type=kind))
        return result

    def _segment_subtitles(self, package: TranslationPackage, transcript: TranscriptPackage, config: SubtitleConfiguration) -> list[Subtitle]:
        output: list[Subtitle] = []
        for item in package.translated_segments:
            tokens = item.translated_text.split()
            if not tokens:
                continue
            max_tokens = max(1, int(config.max_chars_per_line * config.max_lines / max(1, sum(len(t) for t in tokens) / len(tokens))))
            chunks = [tokens[i:i + max_tokens] for i in range(0, len(tokens), max_tokens)]
            mapping_chunks = [item.word_mapping[i:i + max_tokens] for i in range(0, len(item.word_mapping), max_tokens)]
            source_segment = next((seg for seg in transcript.segments if seg.segment_id == item.segment_id), None)
            total = max(0.01, item.end_time - item.start_time)
            for index, chunk in enumerate(chunks):
                maps = mapping_chunks[index] if index < len(mapping_chunks) else []
                start = maps[0].start_time if maps else item.start_time + total * index / len(chunks)
                end = maps[-1].end_time if maps else item.start_time + total * (index + 1) / len(chunks)
                start = max(item.start_time, start)
                end = min(item.end_time, max(start + 0.05, end))
                text = " ".join(chunk).strip()
                important = [m.target_text for m in maps if m.importance_score >= 0.55]
                score = max((m.importance_score for m in maps), default=0.0)
                mode = "KARAOKE" if config.karaoke_enabled else ("DYNAMIC" if config.subtitle_mode.lower() in {"dynamic", "social"} else "STANDARD")
                output.append(Subtitle(id=f"SUB_{len(output)+1:05d}", start_time=start, end_time=end, duration=end-start, text=text, source_segment_ids=[item.segment_id], word_ids=[word_id for m in maps for word_id in m.source_word_ids], word_mapping=maps, speaker_id=item.speaker_id or (source_segment.speaker_id if source_segment else None), caption_mode=mode, highlight_words=important if config.highlight_enabled else [], importance=score, style_hint=config.subtitle_mode, animation_hint="karaoke" if config.karaoke_enabled else ("pop" if important else "minimal"), characters_per_second=len(text) / max(0.01, end-start), words_per_second=len(chunk) / max(0.01, end-start)))
        return self._repair_overlaps(output, config)

    @staticmethod
    def _repair_overlaps(subtitles: list[Subtitle], config: SubtitleConfiguration) -> list[Subtitle]:
        for index, subtitle in enumerate(subtitles):
            if subtitle.duration < config.min_duration:
                subtitle.end_time = subtitle.start_time + config.min_duration
                subtitle.duration = config.min_duration
            if subtitle.duration > config.max_duration:
                subtitle.end_time = subtitle.start_time + config.max_duration
                subtitle.duration = config.max_duration
            if index and subtitle.start_time < subtitles[index-1].end_time + config.min_gap:
                subtitle.start_time = min(subtitle.end_time - 0.05, subtitles[index-1].end_time + config.min_gap)
                subtitle.duration = max(0.05, subtitle.end_time - subtitle.start_time)
        return subtitles

    @staticmethod
    def _translation_quality(items: list[TranslatedSegment]) -> float:
        if not items:
            return 0.0
        return sum(bool(item.translated_text.strip()) for item in items) / len(items)

    @staticmethod
    def _timeline_quality(items: list[Subtitle], config: SubtitleConfiguration) -> float:
        if not items:
            return 0.0
        valid = sum(item.start_time < item.end_time and bool(item.text.strip()) and item.characters_per_second <= config.reading_speed_cps * 1.5 for item in items)
        return valid / len(items)

    def _quality_report(self, subtitles: list[Subtitle], translation: TranslationPackage) -> dict[str, Any]:
        warnings = []
        if any(item.characters_per_second > 30 for item in subtitles):
            warnings.append("FAST_READING_SPEED")
        if any(item.start_time >= item.end_time for item in subtitles):
            warnings.append("INVALID_TIMING")
        return {"translation_quality_score": translation.translation_quality, "subtitle_count": len(subtitles), "warnings": warnings, "status": "QUALITY_GOOD" if not warnings else "QUALITY_WARNING"}
