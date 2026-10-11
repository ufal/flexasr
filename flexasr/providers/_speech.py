"""Speech frames for diarization: MFCC features, energy voice-activity detection, analysis windows."""

from __future__ import annotations

import numpy as np

HOP = 0.010          # s, frame hop
WIN = 0.025          # s, frame length


def _mel_filters(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    def hz2mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel2hz(m):
        return 700.0 * (10 ** (m / 2595.0) - 1.0)

    mels = np.linspace(hz2mel(60.0), hz2mel(sr / 2 - 200.0), n_mels + 2)
    bins = np.floor((n_fft + 1) * mel2hz(mels) / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        a, b, c = bins[i], bins[i + 1], bins[i + 2]
        if b > a:
            fb[i, a:b] = (np.arange(a, b) - a) / (b - a)
        if c > b:
            fb[i, b:c] = (c - np.arange(b, c)) / (c - b)
    return fb


def features(audio: np.ndarray, sr: int, n_mfcc: int = 20) -> tuple[np.ndarray, np.ndarray]:
    """(MFCC frames [n, n_mfcc-1] without c0, log energy per frame [n])."""
    hop, win, n_fft = int(HOP * sr), int(WIN * sr), 512
    if len(audio) < win:
        return np.zeros((0, n_mfcc - 1), np.float32), np.zeros(0, np.float32)
    x = np.append(audio[0], audio[1:] - 0.97 * audio[:-1]).astype(np.float32)   # pre-emphasis
    n = 1 + (len(x) - win) // hop
    idx = np.arange(win)[None, :] + hop * np.arange(n)[:, None]
    frames = x[idx] * np.hamming(win).astype(np.float32)
    power = np.abs(np.fft.rfft(frames, n_fft)) ** 2 / n_fft
    energy = np.log(np.maximum(power.sum(axis=1), 1e-10))
    mel = np.log(np.maximum(power @ _mel_filters(sr, n_fft, 40).T, 1e-10))
    k = np.arange(40)
    dct = np.cos(np.pi / 40 * (k[None, :] + 0.5) * np.arange(n_mfcc)[:, None])   # DCT-II
    mfcc = (mel @ dct.T)[:, 1:]
    return mfcc.astype(np.float32), energy.astype(np.float32)


def speech_mask(energy: np.ndarray, min_speech: float = 0.25, min_silence: float = 0.30) -> np.ndarray:
    if len(energy) == 0:
        return np.zeros(0, bool)
    floor, top = np.percentile(energy, 10), np.percentile(energy, 95)
    mask = energy > floor + 0.35 * (top - floor)
    return _fill(_fill(mask, int(min_silence / HOP), True), int(min_speech / HOP), False)


def _fill(mask: np.ndarray, maxlen: int, value: bool) -> np.ndarray:
    """Turn runs of ``not value`` shorter than ``maxlen`` frames into ``value``."""
    m = mask.copy()
    i, n = 0, len(m)
    while i < n:
        if m[i] != value:
            j = i
            while j < n and m[j] != value:
                j += 1
            if j - i < maxlen and (value or (i > 0 and j < n)):
                m[i:j] = value
            i = j
        else:
            i += 1
    return m


def _windows(mask: np.ndarray, size: int, step: int) -> list[tuple[int, int]]:
    out, i, n = [], 0, len(mask)
    while i < n:
        if not mask[i]:
            i += 1
            continue
        j = i
        while j < n and mask[j]:
            j += 1
        if j - i < size:
            out.append((i, j))
        else:
            out.extend((s, s + size) for s in range(i, j - size + 1, step))
            if (j - i - size) % step:
                out.append((j - size, j))
        i = j
    return out
