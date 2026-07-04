"""Silence / dead-air detection using WebRTC VAD.

Rather than gating cuts on a confidence score (VAD's frame-level speech/silence
call is already quite reliable), safety here comes from a guard-band: every
silence gap we cut is shrunk by `padding_ms` on each side, so a slightly-early
or slightly-late VAD boundary never clips the start/end of a word.
"""
from __future__ import annotations

import wave
from pathlib import Path

import webrtcvad

from .config import Config
from .models import CutAction, CutReason, Decision, Interval

FRAME_MS = 30  # webrtcvad requires 10, 20, or 30 ms frames


def _read_pcm16_mono(wav_path: Path) -> tuple[bytes, int]:
    with wave.open(str(wav_path), "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getnchannels() != 1:
            raise ValueError(
                f"{wav_path} must be mono 16-bit PCM (got {wf.getnchannels()}ch/"
                f"{wf.getsampwidth() * 8}bit) -- extract with media.extract_audio_wav first"
            )
        sample_rate = wf.getframerate()
        if sample_rate not in (8000, 16000, 32000, 48000):
            raise ValueError(f"webrtcvad needs 8/16/32/48kHz, got {sample_rate}")
        return wf.readframes(wf.getnframes()), sample_rate


def _speech_frame_flags(pcm: bytes, sample_rate: int, aggressiveness: int) -> list[bool]:
    vad = webrtcvad.Vad(aggressiveness)
    bytes_per_frame = int(sample_rate * (FRAME_MS / 1000.0)) * 2  # *2 for 16-bit samples
    # Zero-pad so the trailing partial frame still gets classified instead of
    # being silently excluded from both the speech and silence accounting.
    remainder = len(pcm) % bytes_per_frame
    if remainder:
        pcm = pcm + b"\x00" * (bytes_per_frame - remainder)
    flags = []
    for offset in range(0, len(pcm) - bytes_per_frame + 1, bytes_per_frame):
        frame = pcm[offset:offset + bytes_per_frame]
        flags.append(vad.is_speech(frame, sample_rate))
    return flags


def _speech_intervals(flags: list[bool]) -> list[Interval]:
    intervals: list[Interval] = []
    frame_s = FRAME_MS / 1000.0
    start = None
    for i, is_speech in enumerate(flags):
        if is_speech and start is None:
            start = i
        elif not is_speech and start is not None:
            intervals.append(Interval(start * frame_s, i * frame_s))
            start = None
    if start is not None:
        intervals.append(Interval(start * frame_s, len(flags) * frame_s))
    return intervals


def detect_silence(wav_path: Path, clip_duration: float, config: Config) -> list[Decision]:
    """Return CUT decisions for dead-air gaps >= min_silence_duration, padded for safety."""
    pcm, sample_rate = _read_pcm16_mono(wav_path)
    flags = _speech_frame_flags(pcm, sample_rate, config.vad_aggressiveness)
    speech = _speech_intervals(flags)

    # Silence = the gaps between speech intervals (and before the first / after the last).
    boundaries = [0.0] + [t for iv in speech for t in (iv.start, iv.end)] + [clip_duration]
    gaps = [Interval(boundaries[i], boundaries[i + 1]) for i in range(0, len(boundaries) - 1, 2)]

    padding_s = config.padding_ms / 1000.0
    decisions: list[Decision] = []
    for gap in gaps:
        if gap.duration < config.min_silence_duration:
            continue
        padded = Interval(gap.start + padding_s, gap.end - padding_s)
        if padded.duration <= 0:
            continue
        decisions.append(
            Decision(
                interval=padded,
                action=CutAction.CUT,
                reason=CutReason.SILENCE,
                confidence=1.0,
                detail=f"{gap.duration:.2f}s of silence (padded {config.padding_ms}ms each side)",
                detector="silence",
            )
        )
    return decisions
