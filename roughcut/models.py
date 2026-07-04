"""Shared data model: clip + transcript + keep/cut/review decisions.

Every detector module (silence, fillers, duplicates, scenes) consumes a `Clip`
and appends `Decision` objects to it. The assembly stage is the only place
that merges those decisions into final `ResolvedRange`s.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class ClipKind(str, Enum):
    TALKING_HEAD = "talking_head"
    BROLL = "broll"


class CutAction(str, Enum):
    """Decision objects (raw detector output) only ever use CUT/REVIEW -- KEEP is
    never proposed by a detector, it's what's implicitly left over after assembly
    merges everything. ResolvedRange (post-assembly) can be any of the three."""
    KEEP = "keep"      # untouched original footage
    CUT = "cut"        # removed from the rough cut, high confidence
    REVIEW = "review"  # kept in the rough cut, but flagged (low confidence / flag-only detector)


class CutReason(str, Enum):
    SILENCE = "silence"
    FILLER_WORD = "filler_word"
    DUPLICATE_TAKE = "duplicate_take"
    LONG_SHOT = "long_shot"


@dataclass(frozen=True)
class Word:
    text: str
    start: float  # seconds, relative to the clip's own start
    end: float
    confidence: float  # 0..1, derived from the ASR's per-word probability


@dataclass
class Transcript:
    words: list[Word] = field(default_factory=list)
    language: str | None = None
    # Whisper's own sentence/phrase segmentation (acoustic + linguistic), kept
    # separately from the flat `words` list because it's a more reliable
    # utterance boundary for duplicate-take detection than re-deriving one
    # from a fixed pause-duration heuristic.
    segments: list[list[Word]] = field(default_factory=list)

    def words_in(self, start: float, end: float) -> list[Word]:
        return [w for w in self.words if w.start < end and w.end > start]

    @property
    def speech_seconds(self) -> float:
        """Total time covered by words, merging overlaps (words rarely overlap but be safe)."""
        if not self.words:
            return 0.0
        spans = sorted((w.start, w.end) for w in self.words)
        merged: list[list[float]] = []
        for start, end in spans:
            if merged and start <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], end)
            else:
                merged.append([start, end])
        return sum(end - start for start, end in merged)


@dataclass(frozen=True)
class Interval:
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def overlaps(self, other: "Interval") -> bool:
        return self.start < other.end and other.start < self.end

    def intersect(self, other: "Interval") -> "Interval | None":
        start = max(self.start, other.start)
        end = min(self.end, other.end)
        if start >= end:
            return None
        return Interval(start, end)

    def clamp(self, lo: float, hi: float) -> "Interval":
        return Interval(max(self.start, lo), min(self.end, hi))


@dataclass
class Decision:
    """A single detector's opinion about a time range within one clip."""
    interval: Interval
    action: CutAction
    reason: CutReason
    confidence: float  # 0..1, detector's confidence in this specific decision
    detail: str = ""   # human-readable explanation for the report (e.g. matched word/sentence)
    detector: str = ""  # module name, for provenance in the report


@dataclass
class Clip:
    path: Path
    duration: float
    order_index: int
    fps: float = 24.0
    transcript: Transcript = field(default_factory=Transcript)
    kind: ClipKind = ClipKind.BROLL
    speech_coverage: float = 0.0
    has_audio: bool = False
    decisions: list[Decision] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.path.name

    def add_decision(self, decision: Decision) -> None:
        self.decisions.append(decision)


@dataclass
class ResolvedRange:
    """Final keep/cut/review range for one clip, after assembly merges all decisions."""
    clip: Clip
    interval: Interval
    action: CutAction
    reasons: list[Decision] = field(default_factory=list)
