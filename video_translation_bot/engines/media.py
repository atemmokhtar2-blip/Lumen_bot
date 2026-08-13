from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config.settings import Settings


class MediaError(RuntimeError):
    def __init__(self, code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class MediaMetadata:
    duration: float
    width: int | None
    height: int | None
    fps: float | None
    video_codec: str | None
    audio_codec: str | None
    audio_sample_rate: int | None
    audio_channels: int | None
    bitrate: int | None
    container: str | None
    has_video: bool
    has_audio: bool

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


class MediaIntakeEngine:
    def __init__(self, settings: Settings):
        self.settings = settings

    def validate_path(self, path: Path) -> MediaMetadata:
        if not path.exists() or not path.is_file():
            raise MediaError("FILE_NOT_FOUND", "The uploaded media file does not exist.")
        if path.stat().st_size > self.settings.max_file_size_bytes:
            raise MediaError("FILE_TOO_LARGE", "The uploaded file exceeds the configured size limit.")
        metadata = self.probe(path)
        if not metadata.has_video and not metadata.has_audio:
            raise MediaError("NO_MEDIA_STREAM", "The file contains neither a video nor an audio stream.")
        return metadata

    def probe(self, path: Path) -> MediaMetadata:
        if shutil.which(self.settings.ffprobe_bin) is None:
            raise MediaError("FFPROBE_MISSING", "ffprobe is required for media validation.")
        command = [self.settings.ffprobe_bin, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            raise MediaError("INVALID_MEDIA", result.stderr.strip() or "ffprobe rejected the media file.")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise MediaError("INVALID_PROBE_OUTPUT", "Could not parse ffprobe output.") from exc
        streams = payload.get("streams", [])
        video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
        audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
        fmt = payload.get("format", {})
        return MediaMetadata(
            duration=float(fmt.get("duration") or 0.0),
            width=int(video["width"]) if video and video.get("width") else None,
            height=int(video["height"]) if video and video.get("height") else None,
            fps=self._fps(video.get("r_frame_rate")) if video else None,
            video_codec=video.get("codec_name") if video else None,
            audio_codec=audio.get("codec_name") if audio else None,
            audio_sample_rate=int(audio["sample_rate"]) if audio and audio.get("sample_rate") else None,
            audio_channels=int(audio["channels"]) if audio and audio.get("channels") else None,
            bitrate=int(fmt["bit_rate"]) if fmt.get("bit_rate") else None,
            container=fmt.get("format_name"),
            has_video=video is not None,
            has_audio=audio is not None,
        )

    @staticmethod
    def _fps(value: str | None) -> float | None:
        if not value or value in {"0/0", "N/A"}:
            return None
        try:
            numerator, denominator = value.split("/", 1)
            return float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError):
            return None

    def extract_audio(self, input_path: Path, output_path: Path, *, sample_rate: int = 16000, channels: int = 1) -> Path:
        if shutil.which(self.settings.ffmpeg_bin) is None:
            raise MediaError("FFMPEG_MISSING", "ffmpeg is required for audio extraction.")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [self.settings.ffmpeg_bin, "-y", "-i", str(input_path), "-vn", "-ac", str(channels), "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(output_path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=3600)
        if result.returncode != 0 or not output_path.exists():
            raise MediaError("AUDIO_EXTRACTION_FAILED", result.stderr[-1000:] or "Audio extraction failed.", retryable=True)
        return output_path
