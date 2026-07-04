"""Per-clip classification: talking-head (dialogue-driven detectors) vs
b-roll (scene/long-shot detection), based on how much of the clip has speech.

This runs after transcription so no manual folder sorting or filename
convention is required -- the decision is automatic and explainable
(the speech-coverage percentage is recorded and shown in the report).
"""
from __future__ import annotations

from .config import Config
from .models import Clip, ClipKind


def classify_clip(clip: Clip, config: Config) -> None:
    coverage = clip.transcript.speech_seconds / clip.duration if clip.duration > 0 else 0.0
    clip.speech_coverage = coverage
    clip.kind = (
        ClipKind.TALKING_HEAD
        if coverage >= config.speech_coverage_threshold
        else ClipKind.BROLL
    )
