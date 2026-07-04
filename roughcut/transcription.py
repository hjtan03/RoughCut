"""Local transcription via faster-whisper, with word-level timestamps + confidence.

Runs fully offline once the model is downloaded/cached (no cloud API calls).
"""
from __future__ import annotations

from pathlib import Path

from faster_whisper import WhisperModel

from .config import Config
from .models import Transcript, Word

_model_cache: dict[tuple[str, str, str], WhisperModel] = {}


def _get_model(config: Config) -> WhisperModel:
    key = (config.whisper_model, config.whisper_device, config.whisper_compute_type)
    if key not in _model_cache:
        _model_cache[key] = WhisperModel(
            config.whisper_model,
            device=config.whisper_device,
            compute_type=config.whisper_compute_type,
        )
    return _model_cache[key]


def transcribe(audio_path: Path, config: Config) -> Transcript:
    """Transcribe a mono wav (or any ffmpeg-readable audio/video file) with word timestamps."""
    model = _get_model(config)
    segments, info = model.transcribe(
        str(audio_path),
        language=config.whisper_language,
        word_timestamps=True,
        vad_filter=False,  # our own silence detector decides what's dead air, not whisper's VAD
    )

    words: list[Word] = []
    segment_word_lists: list[list[Word]] = []
    for segment in segments:
        if not segment.words:
            continue
        segment_words: list[Word] = []
        for w in segment.words:
            text = w.word.strip()
            if not text:
                continue
            word = Word(
                text=text,
                start=float(w.start),
                end=float(w.end),
                confidence=float(w.probability),
            )
            words.append(word)
            segment_words.append(word)
        if segment_words:
            segment_word_lists.append(segment_words)

    return Transcript(words=words, language=info.language, segments=segment_word_lists)
