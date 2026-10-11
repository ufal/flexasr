"""Clustering diarizers: VAD → windows → embeddings → clustering → turns.

Providers built on :class:`ClusteringDiarizer` only supply ``embed`` (MFCC statistics in builtin_diar, a
neural speaker model in wespeaker_diar). The parts live in small modules: ``_speech`` (features, voice
activity, windows), ``_cluster_algos`` (AHC, threshold, spectral), and here the orchestration and turns.
"""

from __future__ import annotations

import numpy as np

from ..doc import Turn
from ._cluster_algos import _cluster, _cluster_spectral, _cluster_threshold, _silhouette
from ._speech import HOP, WIN, _windows, features, speech_mask  # noqa: F401  (re-exported)
from .base import Diarizer

class ClusteringDiarizer(Diarizer):
    """VAD → windows → ``embed`` → clustering → turns. Subclasses implement ``embed``."""

    min_silhouette = 0.08          # below this, one speaker (no clear second voice)
    stop_similarity: float | None = None   # count speakers by a similarity threshold instead
    clustering: str = "ahc"                # "ahc" (silhouette or threshold) | "spectral" (eigengap)

    def embed(self, audio: np.ndarray, sr: int, wins: list[tuple[int, int]]) -> np.ndarray:
        """One L2-normalised vector per window (frame indices at HOP)."""
        raise NotImplementedError

    def diarize(self, audio, sr, doc, num_speakers=None, min_speakers=None, max_speakers=None):
        opt = self.ctx.options
        _, energy = features(audio, sr)
        mask = speech_mask(energy)
        size, step = int(opt.get("window", 1.5) / HOP), int(opt.get("step", 0.75) / HOP)
        wins = _windows(mask, size, step)
        if not wins:
            return [], []
        emb = self.embed(audio, sr, wins)
        # cluster on windows long enough to identify a voice; short ones join the nearest cluster
        lengths = np.array([b - a for a, b in wins])
        long_idx = np.where(lengths >= float(opt.get("min_cluster_window", 1.0)) / HOP)[0]
        pool = long_idx if len(long_idx) >= 2 else np.arange(len(emb))
        cap = int(opt.get("max_windows", 1500))       # bound time/memory on long recordings
        sample = pool[np.linspace(0, len(pool) - 1, min(cap, len(pool))).astype(int)]
        es = emb[sample]
        thr = opt.get("stop_similarity", self.stop_similarity)
        method = opt.get("clustering", self.clustering)
        if method == "spectral" and len(es) < int(opt.get("spectral_min_windows", 30)):
            method = "ahc"            # too few windows for a reliable eigengap (≈ under 25 s of speech)
        if method == "spectral":
            best_lab = _cluster_spectral(es, min_speakers or 1, max_speakers or 8, fixed_k=num_speakers or 0)
            ks = []
        elif thr is not None and not num_speakers:
            best_lab = _cluster_threshold(es, float(thr), min_speakers or 1, max_speakers or 0)
            ks = []
        elif num_speakers:
            ks = [num_speakers]
        else:
            lo, hi = max(1, min_speakers or 1), min(max_speakers or 6, len(es))
            ks = list(range(max(2, lo), hi + 1)) or [1]
        if ks:
            best_lab = np.zeros(len(es), int)
        best_s = -1.0
        for k in ks:
            lab = _cluster(es, k)
            s = _silhouette(es, lab) if k > 1 else -1.0
            if s > best_s:
                best_lab, best_s = lab, s
        if ks and not num_speakers and (min_speakers or 1) <= 1 and \
                best_s < float(opt.get("min_silhouette", self.min_silhouette)):
            best_lab = np.zeros(len(es), int)
        cents = np.stack([es[best_lab == k].mean(0) for k in np.unique(best_lab)])
        lab_all = np.argmax(emb @ cents.T, axis=1)      # every window to its nearest cluster
        votes = np.zeros((len(mask), len(cents)))
        for (a, b), lab in zip(wins, lab_all):
            votes[a:b, lab] += 1
        frame = np.where(mask & (votes.sum(1) > 0), votes.argmax(1), -1)
        return turns_from_frames(frame, float(opt.get("min_turn", 0.5)))


def turns_from_frames(frame: np.ndarray, min_turn: float) -> tuple[list[Turn], list[Turn]]:
    runs, i, n = [], 0, len(frame)
    while i < n:
        j = i
        while j < n and frame[j] == frame[i]:
            j += 1
        if frame[i] >= 0:
            runs.append([int(frame[i]), i, j])
        i = j
    # absorb short runs into the neighbour they touch, then merge equal neighbours
    changed = True
    while changed and len(runs) > 1:
        changed = False
        for r in range(len(runs)):
            lab, a, b = runs[r]
            if (b - a) * HOP < min_turn:
                nb = runs[r - 1] if r > 0 else runs[r + 1]
                runs[r][0] = nb[0]
                changed = True
        merged = [runs[0]]
        for lab, a, b in runs[1:]:
            if lab == merged[-1][0] and a - merged[-1][2] < int(1.0 / HOP):
                merged[-1][2] = b
            else:
                merged.append([lab, a, b])
        changed = changed and len(merged) < len(runs)
        runs = merged
    order: dict[int, str] = {}
    turns = []
    for lab, a, b in runs:
        name = order.setdefault(lab, f"SPEAKER_{len(order):02d}")
        turns.append(Turn(name, round(a * HOP, 3), round(b * HOP + WIN, 3)))
    return turns, list(turns)
