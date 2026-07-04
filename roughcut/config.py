"""Configuration for the whole pipeline: safe defaults + file/CLI overrides.

Precedence: CLI flags > config file > built-in defaults.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_FILLER_WORDS = [
    "um", "umm", "uh", "uhh", "er", "erm",
    "like", "you know", "sort of", "kind of", "i mean",
]

DEFAULT_VIDEO_EXTENSIONS = (".mp4", ".mov", ".m4v", ".mxf", ".avi", ".mts")


@dataclass
class Config:
    # --- silence / dead air ---
    min_silence_duration: float = 0.75   # gaps >= this many seconds with no speech are cut candidates
    vad_aggressiveness: int = 2          # webrtcvad 0 (least aggressive) .. 3 (most aggressive)
    padding_ms: int = 120                # guard band kept before/after speech so cuts don't clip words

    # --- filler words ---
    filler_words: list[str] = field(default_factory=lambda: list(DEFAULT_FILLER_WORDS))
    filler_cut_confidence: float = 0.60  # ASR word-confidence >= this -> auto-cut; below -> flag for review

    # --- duplicate / false-start takes ---
    duplicate_similarity_threshold: float = 0.82        # rapidfuzz ratio (0..1) -> auto-cut earlier take
    duplicate_review_similarity_threshold: float = 0.65  # below cut threshold but above this -> flag review
    duplicate_min_words: int = 3          # ignore very short utterances, too noisy to compare reliably
    duplicate_utterance_gap: float = 0.5   # pause (s) that splits the transcript into separate utterances

    # --- scene / long shot detection (b-roll only, always flag-only, never auto-cut) ---
    max_shot_length: float = 8.0
    scene_detector_threshold: float = 27.0

    # --- clip classification ---
    speech_coverage_threshold: float = 0.20  # >= this fraction of duration has words -> talking-head pipeline

    # --- transcription ---
    whisper_model: str = "small"
    whisper_language: str | None = None   # None = auto-detect
    whisper_device: str = "auto"
    whisper_compute_type: str = "int8"

    # --- proxy render ---
    proxy_height: int = 480
    proxy_crf: int = 28
    proxy_preset: str = "veryfast"

    # --- misc ---
    conservative: bool = False
    video_extensions: tuple[str, ...] = DEFAULT_VIDEO_EXTENSIONS

    def resolved(self) -> "Config":
        """Return a copy with --conservative adjustments applied, if enabled."""
        if not self.conservative:
            return self
        new_cut_threshold = min(0.97, self.duplicate_similarity_threshold + 0.10)
        return replace(
            self,
            min_silence_duration=self.min_silence_duration * 1.5,
            padding_ms=int(self.padding_ms * 1.5),
            filler_cut_confidence=min(0.95, self.filler_cut_confidence + 0.20),
            duplicate_similarity_threshold=new_cut_threshold,
            # Capped against the NEW cut threshold (not the pre-adjustment one) so
            # the review band can never end up above the cut band, which would
            # make it unreachable in duplicates.py's cut-checked-first if/elif.
            duplicate_review_similarity_threshold=min(
                new_cut_threshold,
                self.duplicate_review_similarity_threshold + 0.10,
            ),
        )

    @classmethod
    def from_file(cls, path: Path) -> "Config":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Config":
        valid = {f.name for f in fields(cls)}
        unknown = set(data) - valid
        if unknown:
            raise ValueError(f"Unknown config key(s): {', '.join(sorted(unknown))}")
        if "filler_words" in data:
            data = dict(data)
            data["filler_words"] = list(data["filler_words"])
        if "video_extensions" in data:
            data = dict(data)
            data["video_extensions"] = tuple(data["video_extensions"])
        return cls(**data)

    def merged_with_overrides(self, overrides: dict[str, Any]) -> "Config":
        """Apply only the keys that are not None (i.e. explicitly passed on the CLI)."""
        clean = {k: v for k, v in overrides.items() if v is not None}
        return replace(self, **clean)
