"""Where someone is speaking: the stretches estimated times are spread over (not the silence between them).

From the diarization turns when there are any (pyannote's segmentation is a good voice-activity detector), else
from the energy of the audio (``providers/_speech.speech_mask``, the same detector the built-in diarizer uses).
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from .doc import Turn
from .providers._speech import HOP, WIN, speech_mask

Regions = list[tuple[float, float]]


def merge(spans: list[tuple[float, float]], gap: float = 0.0) -> Regions:
    out: Regions = []
    for a, b in sorted(spans):
        if b <= a:
            continue
        if out and a <= out[-1][1] + gap:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def from_turns(turns: list[Turn]) -> Regions:
    return merge([(t.start, t.end) for t in turns])


def _log_energy(audio: np.ndarray, sr: int) -> np.ndarray:
    """Log energy per 10 ms frame (25 ms windows), computed in pieces so an hour of audio stays small."""
    hop, win = int(HOP * sr), int(WIN * sr)
    if len(audio) < win:
        return np.zeros(0, np.float32)
    n = 1 + (len(audio) - win) // hop
    out = np.empty(n, np.float32)
    step = 6000                                    # frames per piece (one minute)
    for i in range(0, n, step):
        k = min(step, n - i)
        seg = audio[i * hop: i * hop + (k - 1) * hop + win].astype(np.float32)
        seg = np.append(seg[0], seg[1:] - 0.97 * seg[:-1])                       # pre-emphasis
        sq = np.concatenate([[0.0], np.cumsum(seg.astype(np.float64) ** 2)])
        starts = np.arange(k) * hop
        out[i:i + k] = np.log(np.maximum(sq[starts + win] - sq[starts], 1e-10))
    return out


def from_audio(audio: Optional[np.ndarray], sr: Optional[int]) -> Regions:
    if audio is None or not sr:
        return []
    mask = speech_mask(_log_energy(audio, sr))
    out, i, n = [], 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        out.append((round(i * HOP, 3), round(j * HOP + WIN, 3)))
        i = j
    return merge(out)
