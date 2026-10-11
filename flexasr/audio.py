"""Reading audio as 16 kHz mono float32, the input every stage gets.

Decoders are tried in order (PyAV for any format, soundfile for WAV/FLAC/OGG); a decoder that is not
installed or fails passes on to the next. flexasr decodes with PyAV itself rather than through
faster-whisper's helper, whose PyAV options broke with PyAV 19.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

import numpy as np

from .providers.base import installed

SR = 16000
log = logging.getLogger("flexasr")


def _resample(mono: np.ndarray, sr: int) -> np.ndarray:
    if sr == SR:
        return mono.astype(np.float32)
    n = int(round(len(mono) * SR / sr))
    return np.interp(np.linspace(0, len(mono) - 1, n), np.arange(len(mono)), mono).astype(np.float32)


def _pyav(path: str) -> np.ndarray:
    import av

    resampler = av.AudioResampler(format="s16", layout="mono", rate=SR)
    chunks = []
    with av.open(path, mode="r") as container:
        for frame in container.decode(audio=0):
            for out in resampler.resample(frame):
                chunks.append(out.to_ndarray().reshape(-1))
        for out in resampler.resample(None):             # flush
            chunks.append(out.to_ndarray().reshape(-1))
    if not chunks:
        raise ValueError(f"no audio in {path}")
    return np.concatenate(chunks).astype(np.float32) / 32768.0


def _soundfile(path: str) -> np.ndarray:
    import soundfile as sf

    data, sr = sf.read(path, dtype="float32", always_2d=True)
    return _resample(data.mean(axis=1), sr)


DECODERS: list[tuple[str, str, Callable[[str], np.ndarray]]] = [
    ("pyav", "av", _pyav),
    ("soundfile", "soundfile", _soundfile),
]


def load(path: str | Path) -> tuple[np.ndarray, int]:
    path = str(path)
    errors = []
    for name, module, decode in DECODERS:
        if not installed(module):
            errors.append(f"{name}: not installed")
            continue
        try:
            return decode(path), SR
        except Exception as e:                            # try the next decoder
            log.debug("%s could not decode %s: %s", name, path, e)
            errors.append(f"{name}: {e}")
    raise RuntimeError(f"cannot read audio {path}: " + "; ".join(errors))
