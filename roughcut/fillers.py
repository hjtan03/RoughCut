"""Filler-word detection from the transcript.

Safety: a filler match is only auto-cut when the ASR was confident it actually
heard that word. Low-confidence matches (the model might have misheard
something else as "um") are kept in the timeline and flagged for review
instead of being silently removed.
"""
from __future__ import annotations

from .config import Config
from .models import CutAction, CutReason, Decision, Interval, Transcript, Word
from .textnorm import normalize_text


def detect_fillers(transcript: Transcript, config: Config) -> list[Decision]:
    phrases = sorted(
        (tuple(normalize_text(p).split()) for p in config.filler_words),
        key=len,
        reverse=True,
    )
    phrases = [p for p in phrases if p]

    words = transcript.words
    norm = [normalize_text(w.text) for w in words]

    decisions: list[Decision] = []
    i = 0
    n = len(words)
    while i < n:
        matched: tuple[str, ...] | None = None
        matched_len = 0
        for phrase in phrases:
            plen = len(phrase)
            if i + plen <= n and tuple(norm[i:i + plen]) == phrase:
                matched = phrase
                matched_len = plen
                break
        if matched:
            span: list[Word] = words[i:i + matched_len]
            confidence = min(w.confidence for w in span)
            action = (
                CutAction.CUT
                if confidence >= config.filler_cut_confidence
                else CutAction.REVIEW
            )
            decisions.append(
                Decision(
                    interval=Interval(span[0].start, span[-1].end),
                    action=action,
                    reason=CutReason.FILLER_WORD,
                    confidence=confidence,
                    detail=f"\"{' '.join(w.text for w in span)}\" (ASR confidence {confidence:.2f})",
                    detector="fillers",
                )
            )
            i += matched_len
        else:
            i += 1
    return decisions
