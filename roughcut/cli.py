from __future__ import annotations

import logging
from pathlib import Path

import click

from .config import Config
from .pipeline import process_folder


@click.group()
def main() -> None:
    """RoughCut: turn raw footage into a clean rough-cut cut list for DaVinci Resolve."""


@main.command()
@click.argument("folder", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option("--output", "-o", "output", type=click.Path(file_okay=False, path_type=Path),
              default=Path("./output"), show_default=True, help="Output directory.")
@click.option("--config", "config_path", type=click.Path(exists=True, dir_okay=False, path_type=Path),
              default=None, help="Optional TOML config file overriding defaults.")
@click.option("--min-silence-duration", type=float, default=None,
              help="Silence gaps >= this many seconds are cut candidates. [default: 0.75]")
@click.option("--filler-words", type=str, default=None,
              help="Comma-separated filler word/phrase list, overrides the default list.")
@click.option("--max-shot-length", type=float, default=None,
              help="B-roll static shots longer than this (seconds) are flagged. [default: 8.0]")
@click.option("--duplicate-similarity-threshold", type=float, default=None,
              help="Similarity (0-1) above which an earlier take is auto-cut. [default: 0.82]")
@click.option("--whisper-model", type=str, default=None,
              help="faster-whisper model size/name (tiny/base/small/medium/large-v3...). [default: small]")
@click.option("--whisper-language", type=str, default=None,
              help="Force a transcription language code (e.g. 'en'). [default: auto-detect]")
@click.option("--conservative", is_flag=True, default=None,
              help="Raise all auto-cut thresholds so more borderline cases are flagged instead of cut.")
@click.option("-v", "--verbose", is_flag=True, default=False, help="Verbose logging.")
def process(
    folder: Path,
    output: Path,
    config_path: Path | None,
    min_silence_duration: float | None,
    filler_words: str | None,
    max_shot_length: float | None,
    duplicate_similarity_threshold: float | None,
    whisper_model: str | None,
    whisper_language: str | None,
    conservative: bool | None,
    verbose: bool,
) -> None:
    """Process FOLDER of raw footage into a rough cut in --output."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    config = Config.from_file(config_path) if config_path else Config()

    overrides = {
        "min_silence_duration": min_silence_duration,
        "filler_words": [w.strip() for w in filler_words.split(",")] if filler_words else None,
        "max_shot_length": max_shot_length,
        "duplicate_similarity_threshold": duplicate_similarity_threshold,
        "whisper_model": whisper_model,
        "whisper_language": whisper_language,
        "conservative": conservative,
    }
    config = config.merged_with_overrides(overrides)

    output_dir = process_folder(folder, output, config)
    click.echo(f"Done. Wrote rough_cut.fcpxml, rough_cut.edl, rough_cut_proxy.mp4, cut_report.md to {output_dir}")


if __name__ == "__main__":
    main()
