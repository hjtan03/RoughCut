"""Shared text normalization for word/phrase matching (fillers.py) and
utterance similarity comparison (duplicates.py)."""
from __future__ import annotations

import re

_PUNCT_RE = re.compile(r"[^\w\s']")


def normalize_text(text: str) -> str:
    return _PUNCT_RE.sub("", text).strip().lower()
