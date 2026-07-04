from roughcut.models import Interval, Transcript, Word


def test_interval_overlaps():
    assert Interval(0, 5).overlaps(Interval(4, 10))
    assert not Interval(0, 5).overlaps(Interval(5, 10))
    assert not Interval(0, 5).overlaps(Interval(6, 10))


def test_interval_intersect():
    assert Interval(0, 5).intersect(Interval(3, 10)) == Interval(3, 5)
    assert Interval(0, 5).intersect(Interval(5, 10)) is None


def test_interval_clamp():
    assert Interval(-2, 8).clamp(0, 5) == Interval(0, 5)


def test_transcript_speech_seconds_merges_overlaps():
    t = Transcript(words=[
        Word("a", 0.0, 1.0, 1.0),
        Word("b", 0.9, 2.0, 1.0),  # overlaps with "a"
        Word("c", 5.0, 6.0, 1.0),  # separate
    ])
    assert t.speech_seconds == 3.0  # (0-2) + (5-6)


def test_transcript_words_in():
    t = Transcript(words=[Word("a", 0.0, 1.0, 1.0), Word("b", 2.0, 3.0, 1.0)])
    assert [w.text for w in t.words_in(0.5, 2.5)] == ["a", "b"]
