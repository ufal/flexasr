"""Reading audio as 16 kHz mono float32, the input every stage gets."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

SR = 16000


def load(path: str | Path) -> tuple[np.ndarray, int]:
    """Decode any format PyAV can read (via faster-whisper), else WAV/FLAC via soundfile."""
    path = str(path)
    if importlib.util.find_spec("faster_whisper") is not None:
        from faster_whisper.audio import decode_audio

        return decode_audio(path, sampling_rate=SR).astype(np.float32), SR
    import soundfile as sf

    data, sr = sf.read(path, dtype="float32", always_2d=True)
    mono = data.mean(axis=1)
    if sr != SR:
        n = int(round(len(mono) * SR / sr))
        mono = np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono).astype(np.float32)
    return mono, SR
