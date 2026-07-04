"""Cut-list assembly: merges every detector's decisions for a clip into a
single, non-overlapping partition of that clip's timeline (KEEP / CUT /
REVIEW), then concatenates all clips' keepable ranges in file order into one
rough-cut sequence.

Precedence when decisions overlap: CUT always wins over REVIEW for that
sub-range (if it's being removed, there's nothing left to flag for review).
Everything not covered by a CUT or REVIEW decision is plain KEEP.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import Clip, CutAction, Interval, ResolvedRange


def _merge_intervals(intervals: list[Interval]) -> list[Interval]:
    if not intervals:
        return []
    ordered = sorted(intervals, key=lambda iv: iv.start)
    merged = [ordered[0]]
    for iv in ordered[1:]:
        last = merged[-1]
        if iv.start <= last.end:
            merged[-1] = Interval(last.start, max(last.end, iv.end))
        else:
            merged.append(iv)
    return merged


def _subtract(base: list[Interval], remove: list[Interval]) -> list[Interval]:
    result: list[Interval] = []
    for b in base:
        pieces = [b]
        for r in remove:
            next_pieces: list[Interval] = []
            for p in pieces:
                if not p.overlaps(r):
                    next_pieces.append(p)
                    continue
                if r.start > p.start:
                    next_pieces.append(Interval(p.start, min(r.start, p.end)))
                if r.end < p.end:
                    next_pieces.append(Interval(max(r.end, p.start), p.end))
            pieces = next_pieces
        result.extend(p for p in pieces if p.duration > 0)
    return result


def resolve_clip(clip: Clip) -> list[ResolvedRange]:
    """Partition a single clip's full duration into KEEP/CUT/REVIEW ranges."""
    duration = clip.duration
    cut_decisions = [d for d in clip.decisions if d.action == CutAction.CUT]
    review_decisions = [d for d in clip.decisions if d.action == CutAction.REVIEW]

    cut_mask = _merge_intervals([d.interval.clamp(0, duration) for d in cut_decisions])
    review_mask_raw = _merge_intervals([d.interval.clamp(0, duration) for d in review_decisions])
    review_mask = _subtract(review_mask_raw, cut_mask)

    boundaries = {0.0, duration}
    for iv in (*cut_mask, *review_mask):
        boundaries.add(iv.start)
        boundaries.add(iv.end)
    sorted_bounds = sorted(b for b in boundaries if 0.0 <= b <= duration)

    ranges: list[ResolvedRange] = []
    for start, end in zip(sorted_bounds, sorted_bounds[1:]):
        if end - start <= 1e-6:
            continue
        segment = Interval(start, end)
        midpoint = (start + end) / 2
        if any(iv.start <= midpoint < iv.end for iv in cut_mask):
            action = CutAction.CUT
        elif any(iv.start <= midpoint < iv.end for iv in review_mask):
            action = CutAction.REVIEW
        else:
            action = CutAction.KEEP
        # Only cite decisions whose *own* action matches this segment's resolved
        # action -- a CUT decision's raw interval can spatially overlap a segment
        # that ended up REVIEW (or vice versa) once masks are merged/subtracted,
        # and citing it there would misattribute why that segment got its action.
        reasons = [
            d for d in clip.decisions
            if d.action == action and d.interval.overlaps(segment)
        ]
        ranges.append(ResolvedRange(clip=clip, interval=segment, action=action, reasons=reasons))
    return ranges


@dataclass
class Timeline:
    sequence: list[ResolvedRange]              # KEEP + REVIEW ranges, in final chronological order
    all_ranges: dict[str, list[ResolvedRange]]  # clip path -> full breakdown incl. CUT, for the report


def assemble(clips: list[Clip]) -> Timeline:
    ordered_clips = sorted(clips, key=lambda c: c.order_index)
    all_ranges: dict[str, list[ResolvedRange]] = {}
    sequence: list[ResolvedRange] = []
    for clip in ordered_clips:
        ranges = resolve_clip(clip)
        all_ranges[str(clip.path)] = ranges
        sequence.extend(r for r in ranges if r.action != CutAction.CUT)
    return Timeline(sequence=sequence, all_ranges=all_ranges)
