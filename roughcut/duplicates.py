"""Duplicate / false-start take detection for talking-head footage.

Utterances come primarily from faster-whisper's own segment boundaries
(acoustic + linguistic, and already proven more reliable in practice than a
fixed pause-duration heuristic -- a real self-correction pause can be as
short as ~0.3-0.5s, which a fixed gap threshold can easily misjudge). Each
whisper segment is then optionally split further on an internal pause gap,
as a safety net for the rarer case where whisper lumps two quick repeated
attempts into a single segment.

We compare every utterance against every *later* utterance in the same
clip. Because we only ever look forward, the last occurrence in a chain of
similar utterances never gets a cut/review decision -- it's implicitly kept,
which is exactly the "keep the last take" behavior we want.

Safety: only high-similarity matches are auto-cut. Borderline matches are
flagged for review instead of being removed, since incorrectly discarding a
take that only *sounds* similar is worse than under-cutting.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from .config import Config
from .models import CutAction, CutReason, Decision, Interval, Transcript, Word
from .textnorm import normalize_text


@dataclass
class Utterance:
    words: list[Word]

    @property
    def start(self) -> float:
        return self.words[0].start

    @property
    def end(self) -> float:
        return self.words[-1].end

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def _split_by_gap(words: list[Word], gap_s: float) -> list[Utterance]:
    if not words:
        return []
    utterances: list[Utterance] = []
    current = [words[0]]
    for prev, word in zip(words, words[1:]):
        if word.start - prev.end > gap_s:
            utterances.append(Utterance(current))
            current = [word]
        else:
            current.append(word)
    utterances.append(Utterance(current))
    return utterances


def _utterances(transcript: Transcript, gap_s: float) -> list[Utterance]:
    segments = transcript.segments or [transcript.words]
    return [u for segment_words in segments for u in _split_by_gap(segment_words, gap_s)]


def detect_duplicate_takes(transcript: Transcript, config: Config) -> list[Decision]:
    utterances = _utterances(transcript, config.duplicate_utterance_gap)
    candidates = [u for u in utterances if len(u.words) >= config.duplicate_min_words]
    normalized = [normalize_text(u.text) for u in candidates]

    best_similarity = [0.0] * len(candidates)
    best_match_idx = [-1] * len(candidates)
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            score = fuzz.token_sort_ratio(normalized[i], normalized[j]) / 100.0
            if score > best_similarity[i]:
                best_similarity[i] = score
                best_match_idx[i] = j

    decisions: list[Decision] = []
    for i, utt in enumerate(candidates):
        score = best_similarity[i]
        match_idx = best_match_idx[i]
        if match_idx == -1:
            continue
        if score >= config.duplicate_similarity_threshold:
            action = CutAction.CUT
        elif score >= config.duplicate_review_similarity_threshold:
            action = CutAction.REVIEW
        else:
            continue
        later = candidates[match_idx]
        decisions.append(
            Decision(
                interval=Interval(utt.start, utt.end),
                action=action,
                reason=CutReason.DUPLICATE_TAKE,
                confidence=score,
                detail=(
                    f'earlier take of "{later.text.strip()[:60]}" '
                    f"(similarity {score:.2f}, kept later take at {later.start:.2f}s)"
                ),
                detector="duplicates",
            )
        )
    return decisions
