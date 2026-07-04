"""Orchestrates the full pipeline: discover clips -> transcribe -> detect ->
classify -> assemble -> export + render + report.

Source media is only ever read (ffprobe) or decoded to a temp wav for
analysis -- never modified, moved, or re-encoded in place.
"""
from __future__ import annotations

import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from . import assembly, classify, duplicates, export, fillers, media, proxy, report, scenes, silence, transcription
from .config import Config
from .models import Clip, ClipKind, Transcript

logger = logging.getLogger("roughcut")


def discover_clips(folder: Path, config: Config) -> list[Path]:
    return sorted(
        p for p in folder.rglob("*")
        if p.is_file() and p.suffix.lower() in config.video_extensions
    )


def build_clip(path: Path, order_index: int, tmp_dir: Path, config: Config) -> Clip:
    info = media.probe(path)
    clip = Clip(
        path=path, duration=info.duration, order_index=order_index,
        fps=info.fps, has_audio=info.has_audio,
    )

    if info.has_audio:
        wav_path = tmp_dir / f"{order_index:04d}_{path.stem}.wav"
        media.extract_audio_wav(path, wav_path)
        clip.transcript = transcription.transcribe(wav_path, config)
        clip.decisions.extend(silence.detect_silence(wav_path, clip.duration, config))
    else:
        clip.transcript = Transcript(words=[])

    classify.classify_clip(clip, config)

    if clip.kind == ClipKind.TALKING_HEAD:
        clip.decisions.extend(fillers.detect_fillers(clip.transcript, config))
        clip.decisions.extend(duplicates.detect_duplicate_takes(clip.transcript, config))
    else:
        clip.decisions.extend(scenes.detect_long_shots(path, config))

    return clip


def process_folder(folder: Path, output_dir: Path, config: Config) -> Path:
    config = config.resolved()
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = discover_clips(folder, config)
    if not paths:
        raise ValueError(f"No video files found in {folder} (looked for {config.video_extensions})")

    clips: list[Clip] = []
    skipped: list[str] = []
    with TemporaryDirectory(prefix="roughcut_audio_") as tmp:
        tmp_dir = Path(tmp)
        for i, path in enumerate(paths):
            logger.info("[%d/%d] Processing %s", i + 1, len(paths), path.name)
            try:
                clips.append(build_clip(path, i, tmp_dir, config))
            except media.ProbeError as e:
                logger.warning("Skipping %s: %s", path.name, e)
                skipped.append(path.name)

        if not clips:
            raise ValueError("Every file failed to probe -- nothing to build a rough cut from")

        rates = {c.fps for c in clips}
        if len(rates) > 1:
            logger.warning(
                "Source clips have mixed frame rates (%s). The FCPXML handles this "
                "correctly per-clip, but the EDL fallback uses a single project rate "
                "(%.3ffps) and will have incorrect timecodes for other-rate clips -- "
                "treat the FCPXML as authoritative.",
                sorted(rates), clips[0].fps,
            )

        timeline_data = assembly.assemble(clips)

        otio_timeline = export.build_timeline(timeline_data.sequence)
        export.export_fcpxml(otio_timeline, output_dir / "rough_cut.fcpxml")
        export.export_edl(otio_timeline, output_dir / "rough_cut.edl", clips[0].fps)

        logger.info("Rendering proxy preview...")
        proxy.render_proxy(timeline_data.sequence, output_dir / "rough_cut_proxy.mp4", config)

    report.write_report(clips, timeline_data, config, folder, output_dir / "cut_report.md", skipped)

    return output_dir
