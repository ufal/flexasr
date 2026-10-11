"""Built-in speaker diarization: numpy only, shipped with flexasr, runs on any computer.

The fallback when no better diarizer is usable: no download, no account, no GPU. Embedding per window:
mean and spread of MFCCs (z-scored, L2-normalised); the rest (VAD, clustering, turns) is shared with the
neural diarizers (_clustering.py). It separates clearly different voices reasonably; it is no match for
a speaker model (wespeaker_diar) or pyannote on similar voices, noise or crosstalk.
"""

from __future__ import annotations

import numpy as np

from ._clustering import ClusteringDiarizer, features
from .base import ProviderSpec


class BuiltinDiarizer(ClusteringDiarizer):
    spec = ProviderSpec(
        name="builtin-diar", family="builtin", tasks=("diarize",), devices=("cpu", "mps", "cuda"),
        needs_model=False,
        description="Built-in MFCC + clustering diarization (numpy only, no download, any computer).",
    )

    def embed(self, audio, sr, wins):
        mfcc, _ = features(audio, sr)
        emb = np.stack([np.concatenate([mfcc[a:b].mean(0), mfcc[a:b].std(0)]) for a, b in wins])
        emb = (emb - emb.mean(0)) / (emb.std(0) + 1e-6)
        return emb / (np.linalg.norm(emb, axis=1, keepdims=True) + 1e-9)


PROVIDER = BuiltinDiarizer
