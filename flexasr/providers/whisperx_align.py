"""Forced alignment with WhisperX's default wav2vec2 model per language (fallback aligner)."""

from __future__ import annotations

from .. import langs
from .base import Aligner, ProviderSpec


class WhisperXAlign(Aligner):
    spec = ProviderSpec(
        name="whisperx-align", family="wav2vec2-ctc", tasks=("align",),
        devices=("cuda", "cpu"), requires=("whisperx",), needs_model=False,
        description="WhisperX forced alignment (wav2vec2, default model per language).",
    )

    def version(self):
        from importlib.metadata import version

        return version("whisperx")

    def align(self, audio, sr, doc):
        import whisperx

        code = langs.iso1(doc.language or self.ctx.language)
        if not code:
            raise RuntimeError("whisperx alignment needs a language")
        model, meta = whisperx.load_align_model(language_code=code, device=self.ctx.device,
                                                model_name=self.ctx.options.get("model_name"))
        for u in doc.utterances:
            if not u.words or u.start is None or u.end is None:
                continue
            text = " ".join(w.text for w in u.words)
            res = whisperx.align([{"text": text, "start": u.start, "end": u.end}], model, meta, audio,
                                 self.ctx.device, return_char_alignments=False)
            aligned = [w for s in res.get("segments", []) for w in s.get("words", [])]
            # whisperx returns one entry per whitespace word, in order; keep our words, take times
            if len(aligned) != len(u.words):
                continue
            for w, a in zip(u.words, aligned):
                if a.get("start") is not None and a.get("end") is not None:
                    w.start, w.end = round(a["start"], 3), round(a["end"], 3)
                    if a.get("score") is not None:
                        w.conf = round(float(a["score"]), 3)


PROVIDER = WhisperXAlign
