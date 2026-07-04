"""Scene/shot detection for b-roll: flags overly long static shots.

Per user decision this is flag-only -- it never removes footage on its own.
Long shots are always emitted as REVIEW decisions so they show up as markers
in the exported timeline and in the cut report, but the full shot stays in
the rough cut until you decide in Resolve.
"""
from __future__ import annotations

from pathlib import Path

from scenedetect import ContentDetector, detect

from .config import Config
from .models import CutAction, CutReason, Decision, Interval


def detect_long_shots(video_path: Path, config: Config) -> list[Decision]:
    scene_list = detect(str(video_path), ContentDetector(threshold=config.scene_detector_threshold))

    decisions: list[Decision] = []
    for start_tc, end_tc in scene_list:
        start, end = start_tc.get_seconds(), end_tc.get_seconds()
        duration = end - start
        if duration <= config.max_shot_length:
            continue
        decisions.append(
            Decision(
                interval=Interval(start, end),
                action=CutAction.REVIEW,
                reason=CutReason.LONG_SHOT,
                confidence=1.0,
                detail=(
                    f"static shot is {duration:.1f}s, exceeds max_shot_length "
                    f"of {config.max_shot_length:.1f}s -- review for manual trim in Resolve"
                ),
                detector="scenes",
            )
        )
    return decisions
