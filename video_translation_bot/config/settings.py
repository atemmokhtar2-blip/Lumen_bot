from __future__ import annotations

import os
from pathlib import Path
from pydantic import BaseModel, Field


class Settings(BaseModel):
    data_dir: Path = Field(default=Path(os.getenv("VIDEO_BOT_DATA_DIR", "./data/video_jobs")))
    max_file_size_mb: int = int(os.getenv("VIDEO_BOT_MAX_FILE_SIZE_MB", "2048"))
    worker_count: int = int(os.getenv("VIDEO_BOT_WORKERS", "1"))
    ffmpeg_bin: str = os.getenv("FFMPEG_BIN", "ffmpeg")
    ffprobe_bin: str = os.getenv("FFPROBE_BIN", "ffprobe")
    speech_backend: str = os.getenv("LOCAL_SPEECH_BACKEND", "faster-whisper")
    speech_model: str = os.getenv("LOCAL_SPEECH_MODEL", "small")
    speech_device: str = os.getenv("LOCAL_SPEECH_DEVICE", "cpu")
    speech_compute_type: str = os.getenv("LOCAL_SPEECH_COMPUTE_TYPE", "int8")
    translation_backend: str = os.getenv("LOCAL_TRANSLATION_BACKEND", "argos")
    translation_model: str | None = os.getenv("LOCAL_TRANSLATION_MODEL")
    keep_intermediates: bool = os.getenv("VIDEO_BOT_KEEP_INTERMEDIATES", "0").lower() in {"1", "true", "yes"}
    telegram_token: str | None = os.getenv("TELEGRAM_BOT_TOKEN")

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024

    def ensure(self) -> "Settings":
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self


def get_settings() -> Settings:
    return Settings().ensure()
