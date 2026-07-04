from roughcut.config import Config
from roughcut.fillers import detect_fillers
from roughcut.models import CutAction, CutReason, Transcript, Word


def _config(**overrides) -> Config:
    return Config(**overrides)


def test_single_word_filler_high_confidence_is_cut():
    t = Transcript(words=[
        Word("Well", 0.0, 0.3, 0.99),
        Word("um", 0.3, 0.5, 0.90),
        Word("hello", 0.5, 1.0, 0.99),
    ])
    decisions = detect_fillers(t, _config())
    assert len(decisions) == 1
    d = decisions[0]
    assert d.reason == CutReason.FILLER_WORD
    assert d.action == CutAction.CUT
    assert (d.interval.start, d.interval.end) == (0.3, 0.5)


def test_low_confidence_filler_is_flagged_for_review_not_cut():
    t = Transcript(words=[Word("um", 0.0, 0.2, 0.30)])
    decisions = detect_fillers(t, _config(filler_cut_confidence=0.6))
    assert len(decisions) == 1
    assert decisions[0].action == CutAction.REVIEW


def test_multi_word_filler_phrase_matches_as_one_span():
    t = Transcript(words=[
        Word("you", 0.0, 0.2, 0.95),
        Word("know", 0.2, 0.4, 0.95),
        Word("this", 0.4, 0.6, 0.95),
    ])
    decisions = detect_fillers(t, _config(filler_words=["you know"]))
    assert len(decisions) == 1
    assert (decisions[0].interval.start, decisions[0].interval.end) == (0.0, 0.4)


def test_no_false_positive_on_unrelated_words():
    t = Transcript(words=[Word("hello", 0.0, 0.3, 0.99), Word("world", 0.3, 0.6, 0.99)])
    assert detect_fillers(t, _config()) == []
