from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JobStatus(str, Enum):
    RECEIVED = "RECEIVED"
    DOWNLOADING = "DOWNLOADING"
    VALIDATING = "VALIDATING"
    AUDIO_EXTRACTION = "AUDIO_EXTRACTION"
    AUDIO_PREPROCESSING = "AUDIO_PREPROCESSING"
    SPEECH_ANALYSIS = "SPEECH_ANALYSIS"
    TRANSCRIBING = "TRANSCRIBING"
    TIMING_ALIGNMENT = "TIMING_ALIGNMENT"
    SPEAKER_ANALYSIS = "SPEAKER_ANALYSIS"
    TRANSCRIPT_PROCESSING = "TRANSCRIPT_PROCESSING"
    TRANSLATING = "TRANSLATING"
    SUBTITLE_TIMELINE = "SUBTITLE_TIMELINE"
    RENDER_QUEUED = "RENDER_QUEUED"
    RENDER_PREPARING = "RENDER_PREPARING"
    RENDERING = "RENDERING"
    ENCODING = "ENCODING"
    QUALITY_CHECK = "QUALITY_CHECK"
    EXPORTING = "EXPORTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Word(BaseModel):
    model_config = ConfigDict(extra="allow")
    word_id: str
    text: str
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    speaker_id: str | None = None

    @field_validator("end_time")
    @classmethod
    def valid_end(cls, value: float, info):
        start = info.data.get("start_time")
        if start is not None and value < start:
            raise ValueError("word end_time must be >= start_time")
        return value


class Segment(BaseModel):
    model_config = ConfigDict(extra="allow")
    segment_id: str
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    text: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    speaker_id: str | None = None
    words: list[Word] = Field(default_factory=list)


class QualityReport(BaseModel):
    model_config = ConfigDict(extra="allow")
    speech_coverage: float = Field(default=0.0, ge=0.0, le=1.0)
    average_word_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    language_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    low_confidence_segments: list[str] = Field(default_factory=list)
    silence_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    speaker_count: int = Field(default=0, ge=0)
    timing_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    transcript_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    status: Literal["QUALITY_GOOD", "QUALITY_WARNING", "QUALITY_POOR"] = "QUALITY_WARNING"
    warnings: list[str] = Field(default_factory=list)


class TranscriptPackage(BaseModel):
    model_config = ConfigDict(extra="allow")
    job_id: str
    source_language: str
    language_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    alternative_languages: list[str] = Field(default_factory=list)
    duration: float = Field(default=0.0, ge=0.0)
    speakers: list[str] = Field(default_factory=list)
    segments: list[Segment] = Field(default_factory=list)
    words: list[Word] = Field(default_factory=list)
    raw_transcript: str = ""
    clean_transcript: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
    quality_report: QualityReport = Field(default_factory=QualityReport)


class TranslationMode(str, Enum):
    NATURAL = "natural"
    LITERAL = "literal"
    PROFESSIONAL = "professional"
    SOCIAL = "social"
    CINEMATIC = "cinematic"
    LYRICS = "lyrics"
    EGYPTIAN_ARABIC = "egyptian_arabic"


class SubtitleConfiguration(BaseModel):
    target_language: str = "ar-EG"
    translation_mode: TranslationMode = TranslationMode.NATURAL
    subtitle_mode: str = "standard"
    max_lines: int = Field(default=2, ge=1, le=4)
    max_chars_per_line: int = Field(default=42, ge=8, le=100)
    min_duration: float = Field(default=0.8, ge=0.1)
    max_duration: float = Field(default=7.0, ge=0.5)
    min_gap: float = Field(default=0.04, ge=0.0)
    reading_speed_cps: float = Field(default=17.0, ge=1.0)
    highlight_enabled: bool = True
    karaoke_enabled: bool = False
    caption_density: str = "BALANCED"


class WordMapping(BaseModel):
    source_word_ids: list[str] = Field(default_factory=list)
    target_text: str
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    importance_score: float = Field(default=0.0, ge=0.0, le=1.0)
    importance_type: str | None = None


class TranslatedSegment(BaseModel):
    segment_id: str
    source_text: str
    translated_text: str
    start_time: float
    end_time: float
    speaker_id: str | None = None
    word_mapping: list[WordMapping] = Field(default_factory=list)
    validation_warnings: list[str] = Field(default_factory=list)


class TranslationPackage(BaseModel):
    job_id: str
    source_language: str
    target_language: str
    translation_mode: TranslationMode
    translated_segments: list[TranslatedSegment] = Field(default_factory=list)
    terminology_map: dict[str, str] = Field(default_factory=dict)
    translation_quality: float = Field(default=0.0, ge=0.0, le=1.0)
    context_metadata: dict[str, Any] = Field(default_factory=dict)


class Subtitle(BaseModel):
    id: str
    start_time: float = Field(ge=0)
    end_time: float = Field(ge=0)
    duration: float = Field(ge=0)
    text: str
    source_segment_ids: list[str] = Field(default_factory=list)
    word_ids: list[str] = Field(default_factory=list)
    word_mapping: list[WordMapping] = Field(default_factory=list)
    speaker_id: str | None = None
    caption_mode: str = "STANDARD"
    highlight_words: list[str] = Field(default_factory=list)
    importance: float = Field(default=0.0, ge=0.0, le=1.0)
    position_hint: str = "bottom-center"
    style_hint: str = "standard"
    animation_hint: str = "minimal"
    safe_area_hint: str = "auto"
    characters_per_second: float = 0.0
    words_per_second: float = 0.0


class SubtitleTimeline(BaseModel):
    timeline_id: str = Field(default_factory=lambda: f"TL_{uuid4().hex[:12]}")
    job_id: str
    target_language: str
    mode: str
    subtitles: list[Subtitle] = Field(default_factory=list)
    duration: float = Field(default=0.0, ge=0.0)
    quality_score: float = Field(default=0.0, ge=0.0, le=1.0)


class SubtitlePackage(BaseModel):
    job_id: str
    source_language: str
    target_language: str
    subtitle_timeline: SubtitleTimeline
    translation_package: TranslationPackage
    caption_metadata: dict[str, Any] = Field(default_factory=dict)
    quality_report: dict[str, Any] = Field(default_factory=dict)


class RenderConfiguration(BaseModel):
    style: str = "standard"
    font: str | None = None
    font_size: int | None = Field(default=None, ge=8, le=256)
    position: str = "bottom-center"
    animation: str = "minimal"
    highlight: str = "color"
    highlight_enabled: bool = True
    color: str = "#FFFFFF"
    highlight_color: str = "#FFD54A"
    stroke_color: str = "#000000"
    stroke_width: int = Field(default=2, ge=0, le=20)
    shadow: bool = True
    background: str = "transparent"
    output_resolution: str = "original"
    output_format: str = "mp4"
    aspect_ratio: str = "auto"
    encoding_profile: str = "BALANCED"
    safe_area_profile: str = "auto"
    preserve_audio: bool = True


class RenderJob(BaseModel):
    render_job_id: str = Field(default_factory=lambda: f"RENDER-{uuid4().hex[:12]}")
    job_id: str
    original_video: Path
    subtitle_package: SubtitlePackage
    configuration: RenderConfiguration
    state: str = "RENDER_QUEUED"
    progress: float = Field(default=0.0, ge=0.0, le=1.0)


class FinalVideoPackage(BaseModel):
    job_id: str
    render_job_id: str
    output_path: Path
    duration: float
    resolution: str
    fps: float
    format: str
    file_size: int
    quality_report: dict[str, Any] = Field(default_factory=dict)


class JobRecord(BaseModel):
    job_id: str = Field(default_factory=lambda: f"JOB-{utcnow():%Y%m%d}-{uuid4().hex[:10]}")
    user_id: int
    telegram_file_id: str | None = None
    input_path: Path | None = None
    input_type: str = "unknown"
    file_size: int = 0
    mime_type: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: JobStatus = JobStatus.RECEIVED
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
