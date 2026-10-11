"""Whisper-family transcription through CTranslate2 (faster-whisper).

One provider for the whole family (dev/RESHAPE-2026-10.md §3.0 item 4): Whisper sizes, turbo, and
CTranslate2 conversions of fine-tunes (CrisperWhisper, …) are catalog entries, not code.
"""

from __future__ import annotations

from .. import langs
from ..doc import Utterance, Word
from .base import ProviderSpec, Transcriber


_ATTACH = ("'", "’", "-", "‐")


def merge_pieces(raw) -> list[Word]:
    """Whisper words → signal tokens. A piece without a leading space that starts with an apostrophe
    or hyphen belongs to the previous word ("qu" + "'est" + "-ce" → "qu'est-ce"); other pieces, and
    languages written without spaces, are left as Whisper gives them."""
    out: list[Word] = []
    for w in raw:
        text = w.word
        if not text.strip():
            continue
        if out and not text.startswith(" ") and text.startswith(_ATTACH):
            prev = out[-1]
            prev.text += text
            prev.end = round(w.end, 3)
            prev.conf = round(min(prev.conf or 1.0, w.probability), 3)
            continue
        out.append(Word(text=text.strip(), start=round(w.start, 3), end=round(w.end, 3),
                        conf=round(w.probability, 3)))
    return out


class FasterWhisper(Transcriber):
    spec = ProviderSpec(
        name="faster-whisper", family="whisper-ct2", tasks=("transcribe",),
        modes=("clean", "verbatim"), timestamps="word",
        devices=("cuda", "cpu"),                 # CTranslate2 has no MPS backend
        requires=("faster_whisper",),
        description="Whisper-family models (CTranslate2): word timestamps, VAD filter.",
    )

    def version(self):
        from importlib.metadata import version

        return version("faster-whisper")

    def _model(self):
        from faster_whisper import WhisperModel

        e = self.ctx.entry
        src = e.source if e else None
        if not src or not src.startswith("hf:"):
            raise RuntimeError("faster-whisper needs a catalog entry with an hf: source")
        compute = self.ctx.options.get("compute_type") or ("float16" if self.ctx.device == "cuda" else "int8")
        kwargs = {"device": self.ctx.device, "compute_type": compute,
                  "download_root": self.ctx.options.get("download_root")}
        if e.revision:
            kwargs["revision"] = e.revision      # the pinned revision (reproducible runs)
        return WhisperModel(src[3:], **kwargs)

    def transcribe(self, audio, sr, doc):
        if sr != 16000:
            raise ValueError("faster-whisper expects 16 kHz audio")
        model = self._model()
        opts = dict(self.ctx.options.get("transcribe", {}))
        opts.setdefault("word_timestamps", True)
        opts.setdefault("vad_filter", True)
        opts.setdefault("beam_size", 5)
        if self.ctx.mode == "verbatim":
            # keep what is said: no text conditioning that smooths disfluencies away
            opts.setdefault("condition_on_previous_text", False)
        segments, info = model.transcribe(audio, language=langs.iso1(self.ctx.language), **opts)
        out = []
        for i, seg in enumerate(segments, 1):
            words = merge_pieces(seg.words or [])
            out.append(Utterance(id=f"s{i}", start=round(seg.start, 3), end=round(seg.end, 3),
                                 words=words, text=seg.text.strip()))
        if not doc.language and getattr(info, "language", None):
            doc.language = langs.norm(info.language)
        return out


PROVIDER = FasterWhisper
