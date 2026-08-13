from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config.settings import Settings
from .media import MediaError


@dataclass(frozen=True)
class AudioAnalysis:
    rms_db: float | None = None
    silence_ratio: float = 0.0
    needs_normalization: bool = False


class AudioPreprocessingEngine:
    """Keeps original audio immutable and applies optional conservative preprocessing."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def analyze(self, audio_path: Path) -> AudioAnalysis:
        if shutil.which(self.settings.ffmpeg_bin) is None:
            raise MediaError("FFMPEG_MISSING", "ffmpeg is required for audio analysis.")
        command = [self.settings.ffmpeg_bin, "-hide_banner", "-i", str(audio_path), "-af", "volumedetect", "-f", "null", "-"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=300)
        text = result.stderr
        rms = None
        for line in text.splitlines():
            if "mean_volume:" in line:
                try:
                    rms = float(line.split("mean_volume:", 1)[1].split("dB", 1)[0].strip())
                except ValueError:
                    pass
        return AudioAnalysis(rms_db=rms, needs_normalization=rms is not None and rms < -28.0)

    def preprocess(self, audio_path: Path, output_path: Path, analysis: AudioAnalysis) -> Path:
        if not analysis.needs_normalization:
            return audio_path
        output_path.parent.mkdir(parents=True, exist_ok=True)
        command = [self.settings.ffmpeg_bin, "-y", "-i", str(audio_path), "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "pcm_s16le", str(output_path)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=900)
        if result.returncode != 0 or not output_path.exists():
            raise MediaError("AUDIO_PREPROCESSING_FAILED", result.stderr[-1000:] or "Audio preprocessing failed.", retryable=True)
        return output_path
