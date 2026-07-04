"""ffprobe/ffmpeg helpers. ffmpeg is an external Homebrew dependency (proxy render +
audio extraction only) -- source media is never modified or moved."""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("roughcut")


class FFmpegNotFoundError(RuntimeError):
    pass


class ProbeError(RuntimeError):
    """Raised when ffprobe succeeds but returns unusable data (e.g. no duration)."""


def require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise FFmpegNotFoundError(
            "ffmpeg/ffprobe not found on PATH. Install with `brew install ffmpeg`."
        )


@dataclass(frozen=True)
class MediaInfo:
    duration: float
    fps: float
    has_audio: bool
    width: int
    height: int


def probe(path: Path) -> MediaInfo:
    require_ffmpeg()
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration:stream=codec_type,r_frame_rate,avg_frame_rate,width,height",
                "-of", "json",
                str(path),
            ],
            capture_output=True, text=True, check=True,
        )
    except subprocess.CalledProcessError as e:
        raise ProbeError(f"{path}: ffprobe failed ({e.stderr.strip() or e})")

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        raise ProbeError(f"{path}: ffprobe returned unparseable output ({e})")
    raw_duration = data.get("format", {}).get("duration")
    try:
        duration = float(raw_duration)
    except (TypeError, ValueError):
        raise ProbeError(f"{path}: ffprobe returned no usable duration ({raw_duration!r})")
    if duration <= 0:
        raise ProbeError(f"{path}: ffprobe reported a non-positive duration ({duration})")

    fps = 24.0
    width = height = 0
    has_audio = False
    for stream in data.get("streams", []):
        if stream.get("codec_type") == "video" and width == 0:
            width = int(stream.get("width", 0) or 0)
            height = int(stream.get("height", 0) or 0)
            fps = _parse_rate(
                stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "24/1", path
            )
        elif stream.get("codec_type") == "audio":
            has_audio = True

    return MediaInfo(duration=duration, fps=fps, has_audio=has_audio, width=width, height=height)


def _parse_rate(rate: str, path: Path) -> float:
    fallback = 24.0
    if "/" in rate:
        num, _, den = rate.partition("/")
        try:
            num_f, den_f = float(num), float(den)
            if den_f:
                return num_f / den_f
        except ValueError:
            pass
    else:
        try:
            return float(rate)
        except ValueError:
            pass
    logger.warning("%s: could not parse frame rate %r, defaulting to %sfps", path, rate, fallback)
    return fallback


def extract_audio_wav(src: Path, dst: Path, sample_rate: int = 16000) -> Path:
    """Extract mono PCM16 wav for transcription/VAD. Never touches the source file."""
    require_ffmpeg()
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(src),
            "-vn", "-ac", "1", "-ar", str(sample_rate), "-sample_fmt", "s16",
            str(dst),
        ],
        check=True,
    )
    return dst
