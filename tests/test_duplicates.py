from roughcut.config import Config
from roughcut.duplicates import detect_duplicate_takes
from roughcut.models import CutAction, CutReason, Transcript, Word


def _segment(text: str, start: float, word_dur: float = 0.3, gap: float = 0.05) -> list[Word]:
    words = []
    t = start
    for tok in text.split():
        words.append(Word(tok, t, t + word_dur, 0.95))
        t += word_dur + gap
    return words


def _config(**overrides) -> Config:
    return Config(**overrides)


def test_exact_repeat_cuts_earlier_take_keeps_later():
    seg1 = _segment("the most important thing is safety first", start=0.0)
    seg2 = _segment("the most important thing is safety first", start=10.0)
    t = Transcript(words=seg1 + seg2, segments=[seg1, seg2])

    decisions = detect_duplicate_takes(t, _config())
    assert len(decisions) == 1
    d = decisions[0]
    assert d.reason == CutReason.DUPLICATE_TAKE
    assert d.action == CutAction.CUT
    assert d.interval.start == seg1[0].start
    assert d.interval.end == seg1[-1].end


def test_three_takes_keeps_only_the_last():
    seg1 = _segment("the most important thing is safety first", start=0.0)
    seg2 = _segment("the most important thing is safety first", start=10.0)
    seg3 = _segment("the most important thing is safety first", start=20.0)
    t = Transcript(words=seg1 + seg2 + seg3, segments=[seg1, seg2, seg3])

    decisions = detect_duplicate_takes(t, _config())
    cut_starts = sorted(d.interval.start for d in decisions if d.action == CutAction.CUT)
    assert cut_starts == [seg1[0].start, seg2[0].start]


def test_below_review_threshold_is_ignored():
    seg1 = _segment("completely different sentence about cats", start=0.0)
    seg2 = _segment("another totally unrelated line about dogs", start=10.0)
    t = Transcript(words=seg1 + seg2, segments=[seg1, seg2])

    decisions = detect_duplicate_takes(t, _config())
    assert decisions == []


def test_borderline_similarity_is_flagged_for_review_not_cut():
    seg1 = _segment("the most important thing is safety always", start=0.0)
    seg2 = _segment("the most important thing is speed instead", start=10.0)
    t = Transcript(words=seg1 + seg2, segments=[seg1, seg2])

    decisions = detect_duplicate_takes(
        t, _config(duplicate_similarity_threshold=0.95, duplicate_review_similarity_threshold=0.5)
    )
    assert len(decisions) == 1
    assert decisions[0].action == CutAction.REVIEW


def test_short_utterances_below_min_words_are_ignored():
    seg1 = _segment("okay yeah", start=0.0)
    seg2 = _segment("okay yeah", start=10.0)
    t = Transcript(words=seg1 + seg2, segments=[seg1, seg2])

    decisions = detect_duplicate_takes(t, _config(duplicate_min_words=3))
    assert decisions == []
