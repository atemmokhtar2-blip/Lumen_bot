from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Callable

from .config.settings import Settings
from .engines.local_ai import FasterWhisperSpeechEngine, IdentityTranslationEngine, ArgosTranslationEngine, LocalModelError, SpeechEngine, TranslationEngine
from .engines.media import MediaIntakeEngine, MediaError
from .engines.render import RenderEngine
from .engines.translation import TranslationPipeline
from .models import JobRecord, JobStatus, QualityReport, RenderConfiguration, SubtitleConfiguration, TranscriptPackage

log = logging.getLogger(__name__)


class VideoTranslationPipeline:
    def __init__(self, settings: Settings, *, speech_engine: SpeechEngine | None = None, translation_engine: TranslationEngine | None = None, progress: Callable[[JobRecord, str], None] | None = None):
        self.settings = settings.ensure()
        self.media = MediaIntakeEngine(settings)
        self.speech = speech_engine
        self.translation = translation_engine
        self.render = RenderEngine(settings)
        self.progress = progress or (lambda job, message: log.info("%s %s %s", job.job_id, job.status.value, message))

    def _speech_engine(self) -> SpeechEngine:
        if self.speech is None:
            self.speech = FasterWhisperSpeechEngine(self.settings.speech_model, self.settings.speech_device, self.settings.speech_compute_type)
        return self.speech

    def _translation_engine(self) -> TranslationEngine:
        if self.translation is None:
            if self.settings.translation_backend.lower() == "argos":
                self.translation = ArgosTranslationEngine()
            else:
                self.translation = IdentityTranslationEngine()
        return self.translation

    def process(self, job: JobRecord, *, subtitle_config: SubtitleConfiguration, render_config: RenderConfiguration | None = None) -> Path:
        if not job.input_path:
            raise MediaError("INPUT_PATH_MISSING", "Job input path is missing.")
        root = self.settings.data_dir / job.job_id
        root.mkdir(parents=True, exist_ok=True)
        original = root / "original" / job.input_path.name
        original.parent.mkdir(parents=True, exist_ok=True)
        if job.input_path.resolve() != original.resolve():
            shutil.copy2(job.input_path, original)
        try:
            self._set(job, JobStatus.VALIDATING, 0.05, "validating media")
            metadata = self.media.validate_path(original)
            job.metadata["media"] = metadata.as_dict()
            audio = root / "audio" / "speech.wav"
            self._set(job, JobStatus.AUDIO_EXTRACTION, 0.12, "extracting audio")
            self.media.extract_audio(original, audio)
            self._set(job, JobStatus.TRANSCRIBING, 0.28, "running local speech recognition")
            language, lang_conf, segments, words, speakers = self._speech_engine().transcribe(audio)
            raw = " ".join(segment.text for segment in segments).strip()
            clean = " ".join(raw.split())
            quality = self._quality(segments, words, lang_conf, metadata.duration)
            transcript = TranscriptPackage(job_id=job.job_id, source_language=language, language_confidence=lang_conf, duration=metadata.duration, speakers=speakers, segments=segments, words=words, raw_transcript=raw, clean_transcript=clean, metadata=job.metadata, quality_report=quality)
            (root / "transcript.json").write_text(transcript.model_dump_json(indent=2), encoding="utf-8")
            self._set(job, JobStatus.TRANSLATING, 0.52, "running local translation")
            subtitle_package = TranslationPipeline(self._translation_engine()).build_package(transcript, subtitle_config)
            (root / "subtitle_package.json").write_text(subtitle_package.model_dump_json(indent=2), encoding="utf-8")
            output = root / "output" / f"{job.job_id}.mp4"
            if render_config is None:
                render_config = RenderConfiguration(style=subtitle_config.subtitle_mode, animation="karaoke" if subtitle_config.karaoke_enabled else "minimal", highlight_enabled=subtitle_config.highlight_enabled)
            self._set(job, JobStatus.RENDERING, 0.72, "rendering subtitles locally")
            self.render.render(original, subtitle_package, render_config, output)
            self._set(job, JobStatus.QUALITY_CHECK, 0.94, "quality check completed")
            self._set(job, JobStatus.COMPLETED, 1.0, "completed")
            return output
        except (MediaError, LocalModelError, Exception) as exc:
            job.status = JobStatus.FAILED
            job.error_code = getattr(exc, "code", type(exc).__name__.upper())
            job.error_message = str(exc)
            log.exception("Job %s failed", job.job_id)
            raise

    def _set(self, job: JobRecord, status: JobStatus, progress: float, message: str) -> None:
        job.status, job.progress = status, progress
        self.progress(job, message)

    @staticmethod
    def _quality(segments, words, language_confidence, duration) -> QualityReport:
        spoken = sum(max(0.0, segment.end_time - segment.start_time) for segment in segments)
        avg = sum(word.confidence for word in words) / len(words) if words else 0.0
        low = [segment.segment_id for segment in segments if segment.confidence < 0.45]
        return QualityReport(speech_coverage=min(1.0, spoken / duration) if duration else 0.0, average_word_confidence=avg, language_confidence=language_confidence, low_confidence_segments=low, silence_ratio=max(0.0, 1.0 - (spoken / duration if duration else 0.0)), speaker_count=len({s.speaker_id for s in segments if s.speaker_id}), timing_quality=1.0 if all(s.start_time < s.end_time for s in segments) else 0.0, transcript_quality=1.0 if words else 0.0, status="QUALITY_GOOD" if words and language_confidence >= 0.6 else "QUALITY_WARNING")
