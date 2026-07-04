from pathlib import Path

from roughcut.assembly import assemble, resolve_clip
from roughcut.models import Clip, CutAction, CutReason, Decision, Interval


def _clip(path: str, duration: float, order_index: int, decisions=None) -> Clip:
    c = Clip(path=Path(path), duration=duration, order_index=order_index)
    c.decisions = decisions or []
    return c


def _decision(start, end, action, reason=CutReason.SILENCE, confidence=1.0) -> Decision:
    return Decision(interval=Interval(start, end), action=action, reason=reason, confidence=confidence)


def test_resolve_clip_partitions_full_duration():
    clip = _clip("a.mp4", 10.0, 0, [_decision(2, 4, CutAction.CUT)])
    ranges = resolve_clip(clip)
    assert ranges[0].interval.start == 0.0
    assert ranges[-1].interval.end == 10.0
    # contiguous, no gaps or overlaps
    for a, b in zip(ranges, ranges[1:]):
        assert a.interval.end == b.interval.start


def test_cut_wins_over_overlapping_review():
    clip = _clip("a.mp4", 10.0, 0, [
        _decision(2, 6, CutAction.REVIEW, reason=CutReason.LONG_SHOT),
        _decision(4, 5, CutAction.CUT, reason=CutReason.FILLER_WORD),
    ])
    ranges = resolve_clip(clip)
    by_action = {(r.interval.start, r.interval.end): r.action for r in ranges}
    assert by_action[(4.0, 5.0)] == CutAction.CUT
    assert by_action[(2.0, 4.0)] == CutAction.REVIEW
    assert by_action[(5.0, 6.0)] == CutAction.REVIEW


def test_reasons_only_cite_decisions_matching_the_segments_own_action():
    clip = _clip("a.mp4", 10.0, 0, [
        _decision(2, 6, CutAction.REVIEW, reason=CutReason.LONG_SHOT),
        _decision(4, 5, CutAction.CUT, reason=CutReason.FILLER_WORD),
    ])
    ranges = resolve_clip(clip)
    by_interval = {(r.interval.start, r.interval.end): r for r in ranges}

    cut_range = by_interval[(4.0, 5.0)]
    assert all(d.action == CutAction.CUT for d in cut_range.reasons)
    assert all(d.reason != CutReason.LONG_SHOT for d in cut_range.reasons)

    review_range = by_interval[(2.0, 4.0)]
    assert all(d.action == CutAction.REVIEW for d in review_range.reasons)


def test_untouched_region_is_keep():
    clip = _clip("a.mp4", 10.0, 0, [_decision(2, 4, CutAction.CUT)])
    ranges = resolve_clip(clip)
    keep_ranges = [r for r in ranges if r.action == CutAction.KEEP]
    assert (0.0, 2.0) in [(r.interval.start, r.interval.end) for r in keep_ranges]
    assert (4.0, 10.0) in [(r.interval.start, r.interval.end) for r in keep_ranges]


def test_assemble_orders_clips_and_excludes_cuts():
    clip_b = _clip("b.mp4", 5.0, 1, [_decision(0, 5, CutAction.CUT)])
    clip_a = _clip("a.mp4", 5.0, 0, [])
    timeline = assemble([clip_b, clip_a])  # passed out of order on purpose
    assert [r.clip.name for r in timeline.sequence] == ["a.mp4"]
    assert len(timeline.all_ranges["b.mp4"]) == 1
    assert timeline.all_ranges["b.mp4"][0].action == CutAction.CUT
