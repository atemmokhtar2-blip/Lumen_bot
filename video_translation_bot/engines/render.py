from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ..config.settings import Settings
from ..models import FinalVideoPackage, RenderConfiguration, SubtitlePackage
from .media import MediaError, MediaIntakeEngine


class RenderError(RuntimeError):
    pass


class StyleEngine:
    PRESETS = {
        "standard": {"font_size": 48, "primary": "&H00FFFFFF", "outline": "&H00000000", "outline_width": 2, "bold": 0},
        "cinematic": {"font_size": 52, "primary": "&H00FFFFFF", "outline": "&H00101010", "outline_width": 3, "bold": 0},
        "social": {"font_size": 64, "primary": "&H00FFFFFF", "outline": "&H00000000", "outline_width": 4, "bold": 1},
        "karaoke": {"font_size": 60, "primary": "&H00FFFFFF", "outline": "&H00000000", "outline_width": 3, "bold": 1},
        "minimal": {"font_size": 44, "primary": "&H00FFFFFF", "outline": "&H66000000", "outline_width": 1, "bold": 0},
        "professional": {"font_size": 48, "primary": "&H00FFFFFF", "outline": "&H00000000", "outline_width": 2, "bold": 0},
    }

    def resolve(self, config: RenderConfiguration) -> dict[str, Any]:
        preset = self.PRESETS.get(config.style.lower(), self.PRESETS["standard"]).copy()
        if config.font_size:
            preset["font_size"] = config.font_size
        if config.stroke_width is not None:
            preset["outline_width"] = config.stroke_width
        preset["font_name"] = config.font or "DejaVu Sans"
        return preset


class ASSRenderer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.styles = StyleEngine()

    def write_ass(self, package: SubtitlePackage, config: RenderConfiguration, output: Path, width: int, height: int) -> Path:
        style = self.styles.resolve(config)
        alignment = {"top": 8, "center": 5, "bottom": 2, "bottom-left": 1, "bottom-right": 3, "bottom-center": 2}.get(config.position.lower(), 2)
        margin_v = int(height * (0.12 if height > width else 0.08))
        lines = ["[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "", "[V4+ Styles]", "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding"]
        lines.append(f"Style: Default,{style['font_name']},{style['font_size']},{style['primary']},&H00FFFFFF,{style['outline']},&H80000000,{style['bold']},0,0,0,100,100,0,0,1,{style['outline_width']},{1 if config.shadow else 0},{alignment},50,50,{margin_v},1")
        lines += ["", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
        for subtitle in package.subtitle_timeline.subtitles:
            text = subtitle.text.replace("{", "\\{").replace("}", "\\}")
            if config.highlight_enabled and subtitle.highlight_words and subtitle.word_mapping:
                text = self._highlight_text(subtitle, text)
            lines.append(f"Dialogue: 0,{self._ass_time(subtitle.start_time)},{self._ass_time(subtitle.end_time)},Default,,0,0,0,,{text}")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return output

    @staticmethod
    def _ass_time(seconds: float) -> str:
        total_cs = max(0, round(seconds * 100))
        hours, remainder = divmod(total_cs, 360000)
        minutes, remainder = divmod(remainder, 6000)
        secs, centis = divmod(remainder, 100)
        return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"

    @staticmethod
    def _highlight_text(subtitle, fallback: str) -> str:
        important = {item.lower() for item in subtitle.highlight_words}
        tokens = []
        for token in subtitle.text.split():
            if token.lower().strip(".,!?؛،") in important:
                tokens.append(f"{{\\c&H0055FFFF&\\b1}}{token}{{\\rDefault}}")
            else:
                tokens.append(token)
        return " ".join(tokens) or fallback


class RenderEngine:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.media = MediaIntakeEngine(settings)
        self.ass = ASSRenderer(settings)

    def render(self, video: Path, package: SubtitlePackage, config: RenderConfiguration, output: Path) -> FinalVideoPackage:
        metadata = self.media.validate_path(video)
        if not metadata.has_video:
            raise RenderError("Rendering requires a video stream.")
        workspace = output.parent / f".render-{package.job_id}"
        workspace.mkdir(parents=True, exist_ok=True)
        ass = workspace / "captions.ass"
        self.ass.write_ass(package, config, ass, metadata.width or 1280, metadata.height or 720)
        output.parent.mkdir(parents=True, exist_ok=True)
        preset = {"FAST": ("veryfast", "23"), "BALANCED": ("medium", "20"), "HIGH_QUALITY": ("slow", "18")}.get(config.encoding_profile.upper(), ("medium", "20"))
        command = [self.settings.ffmpeg_bin, "-y", "-i", str(video), "-vf", f"ass={self._filter_path(ass)}", "-c:v", "libx264", "-preset", preset[0], "-crf", preset[1]]
        if config.preserve_audio and metadata.has_audio:
            command += ["-map", "0:v:0", "-map", "0:a:0", "-c:a", "copy"]
        else:
            command += ["-an"]
        command += ["-movflags", "+faststart", str(output)]
        result = subprocess.run(command, capture_output=True, text=True, timeout=7200)
        if result.returncode != 0 or not output.exists() or output.stat().st_size == 0:
            raise RenderError(result.stderr[-2000:] or "FFmpeg rendering failed.")
        final_meta = self.media.probe(output)
        if not final_meta.has_video or (config.preserve_audio and metadata.has_audio and not final_meta.has_audio):
            raise RenderError("Final video QA failed: missing required stream.")
        if not self.settings.keep_intermediates:
            shutil.rmtree(workspace, ignore_errors=True)
        return FinalVideoPackage(job_id=package.job_id, render_job_id=f"RENDER-{package.job_id}", output_path=output, duration=final_meta.duration, resolution=f"{final_meta.width}x{final_meta.height}", fps=final_meta.fps or 0.0, format=config.output_format, file_size=output.stat().st_size, quality_report={"file_exists": True, "video_stream": final_meta.has_video, "audio_stream": final_meta.has_audio, "duration": final_meta.duration, "resolution": f"{final_meta.width}x{final_meta.height}", "fps": final_meta.fps})

    @staticmethod
    def _filter_path(path: Path) -> str:
        return str(path).replace("\\", "/").replace(":", "\\:")
