"""CrisperWhisper 2.0: verbatim transcription (fillers, repetitions, false starts) with word times.

Runs through the ``crisperwhisper`` package (MIT), on its transformers backend; on its faster
CTranslate2 backend only when nyra's ctranslate2 fork is installed (``ctranslate2-crisperwhisper``,
which replaces the upstream ctranslate2 that faster-whisper needs — so that is a choice per environment). The weights *and their outputs* are under nyra health's
Non-Commercial Research License: catalog entries mark them restricted, so they are only used when
restricted models are allowed, and the output records the restriction.

The model is downloaded at the catalog's pinned revision and passed to the package as a local
directory (the package itself would always take the latest revision).
"""

from __future__ import annotations

from .. import langs
from ..doc import Word
from ._words import utterances_from_words
from .base import ProviderSpec, Transcriber

_FILES = ["*.json", "*.bin", "*.safetensors", "*.txt", "*.model"]


def _ct2_fork() -> bool:
    """Is nyra's ctranslate2 fork installed (the CT2 backend needs its extra decoding APIs)?"""
    try:
        import ctranslate2

        return hasattr(ctranslate2.models.Whisper, "prefill")
    except Exception:
        return False


class CrisperWhisper(Transcriber):
    spec = ProviderSpec(
        name="crisperwhisper", family="crisperwhisper", tasks=("transcribe",),
        modes=("verbatim", "clean"), timestamps="word",
        devices=("cuda", "cpu"),                 # neither backend uses MPS
        requires=("crisperwhisper", "huggingface_hub"),
        description="CrisperWhisper 2.0: verbatim or intended transcription with word times.",
    )

    def version(self):
        from importlib.metadata import version

        return "crisperwhisper " + version("crisperwhisper")

    def _local_dir(self) -> str:
        from huggingface_hub import snapshot_download

        e = self.ctx.entry
        if not e or not (e.source or "").startswith("hf:"):
            raise RuntimeError("crisperwhisper needs a catalog entry with an hf: source")
        return snapshot_download(e.source[3:], revision=e.revision, allow_patterns=_FILES)

    def _settings(self) -> dict:
        o = self.ctx.options
        backend = o.get("backend") or ("ct2" if _ct2_fork() else "transformers")
        if o.get("compute_type"):
            compute = o["compute_type"]
        elif self.ctx.device == "cuda":
            compute = "float16"
        else:
            compute = "int8" if backend == "ct2" else "float32"
        return {"backend": backend, "compute_type": compute, "device": self.ctx.device}

    def transcribe(self, audio, sr, doc):
        from crisperwhisper import CrisperWhisperModel

        model = CrisperWhisperModel(self._local_dir(), **self._settings())
        opts = dict(self.ctx.options.get("transcribe", {}))
        mode = "verbatim" if self.ctx.mode == "verbatim" else "intended"
        res = model.transcribe(audio, sr=sr, language=langs.iso1(self.ctx.language) or "en", mode=mode,
                               word_timestamps=True, **opts)
        words = [Word(text=w.word.strip(), start=round(w.start, 3), end=round(w.end, 3))
                 for w in (res.words or []) if w.word.strip() and w.start is not None]
        return utterances_from_words(words, float(self.ctx.options.get("utterance_gap", 1.0)))


PROVIDER = CrisperWhisper
