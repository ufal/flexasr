"""Aligner that keeps the transcriber's own word times (no separate alignment)."""

from __future__ import annotations

from .base import Aligner, ProviderSpec


class NativeTimestamps(Aligner):
    spec = ProviderSpec(
        name="native", family="none", tasks=("align",), devices=("cpu", "mps", "cuda"),
        needs_model=False, description="Keep the word times produced by the transcriber.",
    )

    def align(self, audio, sr, doc):
        missing = [w.text for w in doc.words() if w.start is None or w.end is None]
        if missing:
            raise RuntimeError(
                f"{len(missing)} word(s) have no times (the transcriber gives no word timestamps); "
                "choose an aligner (e.g. --provider align=whisperx-align)")


PROVIDER = NativeTimestamps
