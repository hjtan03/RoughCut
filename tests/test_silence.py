import struct
import wave
from pathlib import Path

from roughcut import silence
from roughcut.config import Config
from roughcut.models import CutAction, CutReason, Interval


def _write_silent_wav(path: Path, duration_s: float, sample_rate: int = 16000) -> None:
    n_samples = int(duration_s * sample_rate)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{n_samples}h", *([0] * n_samples)))


def test_speech_intervals_merges_consecutive_frames():
    flags = [False, True, True, True, False, False, True, False]
    frame_s = silence.FRAME_MS / 1000.0
    assert silence._speech_intervals(flags) == [
        Interval(1 * frame_s, 4 * frame_s),
        Interval(6 * frame_s, 7 * frame_s),
    ]


def test_detect_silence_finds_gap_and_applies_padding(tmp_path, monkeypatch):
    wav_path = tmp_path / "test.wav"
    _write_silent_wav(wav_path, duration_s=5.0)

    frame_s = silence.FRAME_MS / 1000.0
    n_frames = int(5.0 / frame_s)
    speech_frames = int(1.0 / frame_s)
    # speech 0-1s, silence 1-4s, speech 4-5s
    flags = [True] * speech_frames + [False] * (n_frames - 2 * speech_frames) + [True] * speech_frames
    monkeypatch.setattr(silence, "_speech_frame_flags", lambda pcm, sr, agg: flags)

    decisions = silence.detect_silence(wav_path, clip_duration=5.0, config=Config(padding_ms=100))

    assert len(decisions) == 1
    d = decisions[0]
    assert d.reason == CutReason.SILENCE
    assert d.action == CutAction.CUT
    assert 1.0 < d.interval.start < 1.2
    assert 3.8 < d.interval.end < 4.0


def test_detect_silence_ignores_gaps_shorter_than_threshold(tmp_path, monkeypatch):
    wav_path = tmp_path / "test.wav"
    _write_silent_wav(wav_path, duration_s=3.0)
    frame_s = silence.FRAME_MS / 1000.0
    n_frames = int(3.0 / frame_s)
    flags = [True] * n_frames
    monkeypatch.setattr(silence, "_speech_frame_flags", lambda pcm, sr, agg: flags)

    decisions = silence.detect_silence(wav_path, clip_duration=3.0, config=Config())
    assert decisions == []
