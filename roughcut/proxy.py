"""Renders a quick low-res preview MP4 of the assembled rough cut for review
before opening Resolve. This is the ONLY place source footage gets re-encoded
-- the FCPXML export always references original media untouched."""
from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .config import Config
from .media import require_ffmpeg
from .models import ResolvedRange


def _canonical_dimensions(height: int) -> tuple[int, int]:
    """A single fixed WxH every segment gets padded to, regardless of the
    source's own aspect ratio -- concat's stream-copy pass requires identical
    frame dimensions across all segments, and a folder can mix portrait phone
    clips with landscape camera clips."""
    height += height % 2
    width = round(height * 16 / 9)
    width += width % 2
    return width, height


def render_proxy(sequence: list[ResolvedRange], output_path: Path, config: Config) -> Path:
    require_ffmpeg()
    if not sequence:
        raise ValueError("Nothing to render: the rough cut is empty")

    width, height = _canonical_dimensions(config.proxy_height)
    scale_pad = (
        f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black"
    )

    with tempfile.TemporaryDirectory(prefix="roughcut_proxy_") as tmp:
        tmp_dir = Path(tmp)
        segment_paths: list[Path] = []

        for i, rng in enumerate(sequence):
            duration = rng.interval.duration
            if duration <= 0:
                continue
            seg_path = tmp_dir / f"seg_{i:05d}.mp4"
            encode_args = [
                "-vf", scale_pad,
                "-c:v", "libx264", "-preset", config.proxy_preset, "-crf", str(config.proxy_crf),
                "-c:a", "aac", "-ar", "48000", "-ac", "2",
            ]
            if rng.clip.has_audio:
                cmd = [
                    "ffmpeg", "-y", "-v", "error",
                    "-ss", f"{rng.interval.start:.3f}",
                    "-i", str(rng.clip.path),
                    "-t", f"{duration:.3f}",
                    "-map", "0:v:0", "-map", "0:a:0",
                    *encode_args,
                    str(seg_path),
                ]
            else:
                cmd = [
                    "ffmpeg", "-y", "-v", "error",
                    "-ss", f"{rng.interval.start:.3f}",
                    "-i", str(rng.clip.path),
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                    "-t", f"{duration:.3f}",
                    "-map", "0:v:0", "-map", "1:a:0",
                    *encode_args,
                    str(seg_path),
                ]
            subprocess.run(cmd, check=True)
            segment_paths.append(seg_path)

        if not segment_paths:
            raise ValueError("Nothing to render: every range had zero duration")

        concat_list = tmp_dir / "concat.txt"
        concat_list.write_text("\n".join(f"file '{p.as_posix()}'" for p in segment_paths))

        output_path.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-y", "-v", "error",
                "-f", "concat", "-safe", "0", "-i", str(concat_list),
                "-c", "copy",
                str(output_path),
            ],
            check=True,
        )

    return output_path
