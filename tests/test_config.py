import pytest

from roughcut.config import Config


def test_conservative_raises_thresholds():
    base = Config()
    conservative = Config(conservative=True).resolved()
    assert conservative.min_silence_duration > base.min_silence_duration
    assert conservative.padding_ms > base.padding_ms
    assert conservative.filler_cut_confidence > base.filler_cut_confidence
    assert conservative.duplicate_similarity_threshold > base.duplicate_similarity_threshold


def test_non_conservative_unchanged():
    base = Config()
    assert base.resolved() is base


def test_merged_with_overrides_ignores_none():
    base = Config(min_silence_duration=0.75)
    merged = base.merged_with_overrides({"min_silence_duration": None, "max_shot_length": 5.0})
    assert merged.min_silence_duration == 0.75
    assert merged.max_shot_length == 5.0


def test_from_dict_rejects_unknown_keys():
    with pytest.raises(ValueError):
        Config.from_dict({"not_a_real_field": 1})


def test_from_dict_builds_config():
    cfg = Config.from_dict({"filler_words": ["um", "uh"], "max_shot_length": 6.0})
    assert cfg.filler_words == ["um", "uh"]
    assert cfg.max_shot_length == 6.0
