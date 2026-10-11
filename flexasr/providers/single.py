"""Diarizer that needs nothing: one speaker for the whole recording (the always-available fallback)."""

from __future__ import annotations

from ..doc import Turn
from .base import Diarizer, ProviderSpec


class SingleSpeaker(Diarizer):
    spec = ProviderSpec(
        name="single", family="none", tasks=("diarize",), devices=("cpu", "mps", "cuda"),
        needs_model=False, description="One speaker for the whole recording.",
    )

    def diarize(self, audio, sr, doc, num_speakers=None, min_speakers=None, max_speakers=None):
        dur = len(audio) / sr if sr else (doc.audio.duration or 0.0)
        turns = [Turn("SPEAKER_00", 0.0, round(dur, 3))]
        return turns, list(turns)


PROVIDER = SingleSpeaker
