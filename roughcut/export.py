"""Build an OTIO timeline from the assembled cut list and export FCPXML
(primary, for DaVinci Resolve) + EDL (fallback).

Clips reference the ORIGINAL source media at their original paths via
file:// URLs and original in/out timecodes -- nothing is re-encoded or
copied here. REVIEW-flagged ranges get a yellow marker on the timeline so
they're visible right on the clip in Resolve, not just in the report.
"""
from __future__ import annotations

from pathlib import Path

import opentimelineio as otio
from opentimelineio.opentime import RationalTime, TimeRange

from .models import CutAction, ResolvedRange


def _rt(seconds: float, fps: float) -> RationalTime:
    frame = round(seconds * fps)
    return RationalTime(frame, fps)


def build_timeline(sequence: list[ResolvedRange], name: str = "RoughCut") -> otio.schema.Timeline:
    timeline = otio.schema.Timeline(name=name)
    video_track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
    audio_track = otio.schema.Track(name="A1", kind=otio.schema.TrackKind.Audio)
    timeline.tracks.append(video_track)
    timeline.tracks.append(audio_track)

    media_refs: dict[str, otio.schema.ExternalReference] = {}

    for rng in sequence:
        clip = rng.clip
        fps = clip.fps
        path_str = str(clip.path)
        if path_str not in media_refs:
            media_refs[path_str] = otio.schema.ExternalReference(
                target_url=clip.path.resolve().as_uri(),
                available_range=TimeRange(
                    start_time=RationalTime(0, fps),
                    duration=_rt(clip.duration, fps),
                ),
            )

        start = _rt(rng.interval.start, fps)
        end = _rt(rng.interval.end, fps)
        duration = end - start
        if duration.value <= 0:
            # assembly only ever puts KEEP/REVIEW ranges in `sequence` (CUT is
            # excluded already), so a sub-frame sliver here is footage assembly
            # explicitly decided to keep -- round up to the smallest representable
            # unit (1 frame) instead of silently dropping it from the export.
            duration = RationalTime(1, fps)

        clip_name = f"{clip.name} [{rng.interval.start:.2f}-{rng.interval.end:.2f}]"
        source_range = TimeRange(start_time=start, duration=duration)

        video_clip = otio.schema.Clip(
            name=clip_name, media_reference=media_refs[path_str], source_range=source_range,
        )

        if rng.action == CutAction.REVIEW:
            reason_names = sorted({d.reason.value for d in rng.reasons})
            detail = "; ".join(d.detail for d in rng.reasons if d.detail)
            marker = otio.schema.Marker(
                name=f"REVIEW: {', '.join(reason_names)}",
                marked_range=TimeRange(start_time=start, duration=duration),
                color=otio.schema.MarkerColor.YELLOW,
                metadata={"roughcut": {"detail": detail}},
            )
            video_clip.markers.append(marker)

        video_track.append(video_clip)

        # Mirror onto a parallel audio track so the exported asset is correctly
        # declared as having audio (the fcpx_xml adapter infers hasAudio/hasVideo
        # per-asset from which track kinds actually reference it).
        if clip.has_audio:
            audio_track.append(
                otio.schema.Clip(
                    name=clip_name,
                    media_reference=media_refs[path_str],
                    source_range=source_range,
                )
            )
        else:
            audio_track.append(otio.schema.Gap(source_range=TimeRange(
                start_time=RationalTime(0, fps), duration=duration,
            )))

    return timeline


def export_fcpxml(timeline: otio.schema.Timeline, path: Path) -> None:
    otio.adapters.write_to_file(timeline, str(path), adapter_name="fcpx_xml")


def export_edl(timeline: otio.schema.Timeline, path: Path, fps: float) -> None:
    otio.adapters.write_to_file(timeline, str(path), adapter_name="cmx_3600", rate=fps)
