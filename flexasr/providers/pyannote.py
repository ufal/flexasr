"""pyannote.audio 4 diarization: full (overlapping) and exclusive turns."""

from __future__ import annotations

from ..doc import Turn
from .base import Diarizer, ProviderSpec


class Pyannote(Diarizer):
    spec = ProviderSpec(
        name="pyannote", family="pyannote", tasks=("diarize",),
        devices=("cuda", "mps", "cpu"), requires=("pyannote.audio", "torch"), needs_token=True,
        description="pyannote.audio 4.x pipelines (community-1): overlap-aware and exclusive turns.",
    )

    def version(self):
        from importlib.metadata import version

        return version("pyannote.audio")

    def diarize(self, audio, sr, doc, num_speakers=None, min_speakers=None, max_speakers=None):
        import torch
        from pyannote.audio import Pipeline

        e = self.ctx.entry
        if not e or not (e.source or "").startswith("hf:"):
            raise RuntimeError("pyannote needs a catalog entry with an hf: source")
        kwargs = {"token": self.ctx.token} if self.ctx.token else {}
        if e.revision:
            kwargs["revision"] = e.revision
        pipe = Pipeline.from_pretrained(e.source[3:], **kwargs)
        if pipe is None:
            raise RuntimeError(f"could not load {e.source} (gated model: accept its conditions on "
                               "Hugging Face and set HF_TOKEN)")
        pipe.to(torch.device(self.ctx.device))
        params = {k: v for k, v in (("num_speakers", num_speakers), ("min_speakers", min_speakers),
                                     ("max_speakers", max_speakers)) if v is not None}
        wav = torch.from_numpy(audio).float().unsqueeze(0)
        out = pipe({"waveform": wav, "sample_rate": sr}, **params)
        full = getattr(out, "speaker_diarization", out)
        excl = getattr(out, "exclusive_speaker_diarization", None) or full

        def turns(annotation):
            return [Turn(str(spk), round(seg.start, 3), round(seg.end, 3))
                    for seg, _, spk in annotation.itertracks(yield_label=True)]

        return turns(full), turns(excl)


PROVIDER = Pyannote
