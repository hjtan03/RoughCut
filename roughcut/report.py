"""Markdown cut report: every cut made and why, plus a Needs Review section
for low-confidence / flag-only decisions that were kept in the timeline."""
from __future__ import annotations

from pathlib import Path

from .assembly import Timeline
from .config import Config
from .models import Clip, CutAction, CutReason

REASON_LABELS = {
    CutReason.SILENCE: "Silence / dead air",
    CutReason.FILLER_WORD: "Filler word",
    CutReason.DUPLICATE_TAKE: "Duplicate / false-start take",
    CutReason.LONG_SHOT: "Long static shot",
}


def _fmt_ts(seconds: float) -> str:
    minutes, secs = divmod(max(0.0, seconds), 60)
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours:02d}:{int(minutes):02d}:{secs:06.3f}"


def _reason_summary(reasons) -> tuple[str, str]:
    labels = ", ".join(sorted({REASON_LABELS[d.reason] for d in reasons}))
    details = "; ".join(d.detail for d in reasons if d.detail)
    return labels, details


def _render_range_list(lines: list[str], title: str, ranges) -> None:
    if not ranges:
        return
    lines.append(f"**{title} ({len(ranges)}):**")
    lines.append("")
    for r in ranges:
        labels, details = _reason_summary(r.reasons)
        lines.append(
            f"- `{_fmt_ts(r.interval.start)}`–`{_fmt_ts(r.interval.end)}` "
            f"({r.interval.duration:.2f}s) -- {labels}: {details}"
        )
    lines.append("")


def generate_report(
    clips: list[Clip], timeline: Timeline, config: Config, source_folder: Path,
    skipped: list[str] | None = None,
) -> str:
    lines: list[str] = ["# RoughCut Report", "", f"Source folder: `{source_folder}`", ""]

    if skipped:
        lines += [
            "## Skipped files",
            "",
            "These could not be probed (corrupt/unreadable) and were excluded entirely:",
            "",
        ]
        lines += [f"- {name}" for name in skipped]
        lines.append("")

    total_original = sum(c.duration for c in clips)
    total_kept = sum(r.interval.duration for r in timeline.sequence)
    total_cut = total_original - total_kept
    pct_cut = (total_cut / total_original * 100) if total_original else 0.0

    lines += [
        "## Summary",
        "",
        f"- Clips processed: {len(clips)}",
        f"- Original total duration: {_fmt_ts(total_original)}",
        f"- Rough cut duration: {_fmt_ts(total_kept)}",
        f"- Removed: {_fmt_ts(total_cut)} ({pct_cut:.1f}%)",
        "",
    ]

    review_items = [
        (path, r)
        for path, ranges in timeline.all_ranges.items()
        for r in ranges
        if r.action == CutAction.REVIEW
    ]
    lines += [f"## Needs Review ({len(review_items)})", ""]
    if review_items:
        lines.append(
            "Kept in the rough cut but flagged as low-confidence or flag-only decisions "
            "-- check these in Resolve before your final edit (also marked as yellow markers "
            "on the timeline in the FCPXML import).\n"
        )
        for path, r in review_items:
            labels, details = _reason_summary(r.reasons)
            lines.append(
                f"- **{Path(path).name}** `{_fmt_ts(r.interval.start)}`–`{_fmt_ts(r.interval.end)}` "
                f"-- {labels}: {details}"
            )
    else:
        lines.append("Nothing flagged.")
    lines.append("")

    lines += ["## Cuts by Clip", ""]
    for clip in sorted(clips, key=lambda c: c.order_index):
        ranges = timeline.all_ranges[str(clip.path)]
        cuts = [r for r in ranges if r.action == CutAction.CUT]
        reviews = [r for r in ranges if r.action == CutAction.REVIEW]
        kind_label = "talking-head" if clip.kind.value == "talking_head" else "b-roll"

        lines.append(f"### {clip.name}")
        lines.append(
            f"_{kind_label}, {clip.speech_coverage * 100:.0f}% speech coverage, "
            f"{_fmt_ts(clip.duration)} total_"
        )
        lines.append("")

        if not cuts and not reviews:
            lines.append("No cuts or flags -- kept as-is.")
            lines.append("")
            continue

        _render_range_list(lines, "Cuts", cuts)
        _render_range_list(lines, "Flagged for review", reviews)

    return "\n".join(lines)


def write_report(
    clips: list[Clip], timeline: Timeline, config: Config, source_folder: Path, output_path: Path,
    skipped: list[str] | None = None,
) -> Path:
    text = generate_report(clips, timeline, config, source_folder, skipped)
    output_path.write_text(text)
    return output_path
