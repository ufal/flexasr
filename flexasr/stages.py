"""The stages, one small function each, registered by name.

A stage takes the Doc, the run settings and a :class:`Run` (audio, progress callback, provider
factory) and changes the Doc. Adding a stage is adding a function here and an entry in ``STAGES``;
the pipeline loop never grows.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Callable, Optional

from .assign import assign as assign_speakers
from .disfluency import encode as encode_disfluencies
from .tokens import split_punctuation

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np

    from .doc import Doc
    from .pipeline import Settings


@dataclass
class Run:
    wav: Optional["np.ndarray"]
    sr: Optional[int]
    progress: Callable[[str], None]
    provider: Callable                       # (stage, settings, doc) -> (provider, provenance)


def diarize(doc: "Doc", s: "Settings", r: Run) -> None:
    prov, rec = r.provider("diarize", s, doc)
    r.progress(f"diarize: {rec.provider} ({rec.model or '-'}) on {rec.settings['device']}")
    doc.turns, doc.turns_exclusive = prov.diarize(r.wav, r.sr, doc, s.num_speakers, s.min_speakers,
                                                  s.max_speakers)
    doc.provenance.append(rec)


def transcribe(doc: "Doc", s: "Settings", r: Run) -> None:
    prov, rec = r.provider("transcribe", s, doc)
    r.progress(f"transcribe: {rec.provider} ({rec.model}) on {rec.settings['device']}")
    doc.utterances = prov.transcribe(r.wav, r.sr, doc)
    doc.provenance.append(rec)


def align(doc: "Doc", s: "Settings", r: Run) -> None:
    timed = all(w.start is not None and w.end is not None for w in doc.words())
    if timed and "align" not in s.providers and "align" not in s.models:
        s = replace(s, providers={**s.providers, "align": "native"})   # words already have times
    prov, rec = r.provider("align", s, doc)
    r.progress(f"align: {rec.provider} ({rec.model or '-'})")
    prov.align(r.wav, r.sr, doc)
    doc.provenance.append(rec)


def tokens(doc: "Doc", s: "Settings", r: Run) -> None:
    n = split_punctuation(doc)                # punctuation as separate tokens without times
    r.progress(f"tokens: {n} punctuation token(s) split off (no times)")


def assign(doc: "Doc", s: "Settings", r: Run) -> None:
    if not (doc.turns or doc.turns_exclusive):
        raise RuntimeError("assign needs diarization turns (run the diarize stage)")
    assign_speakers(doc, s.speaker_map, s.untokenized_roles, s.split_gap)
    r.progress(f"assign: {len(doc.speakers)} speaker(s), {len(doc.utterances)} utterance(s)")


def encode(doc: "Doc", s: "Settings", r: Run) -> None:
    if doc.mode != "verbatim":
        return
    encode_disfluencies(doc, doc.language, s.pause_min)
    n = sum(1 for w in doc.words() if w.kind not in ("word", "punct"))
    r.progress(f"encode: {n} disfluency mark(s), {len(doc.pauses)} pause(s)")


STAGES: dict[str, Callable] = {
    "diarize": diarize, "transcribe": transcribe, "align": align,
    "tokens": tokens, "assign": assign, "encode": encode,
}
NEEDS_AUDIO = {"diarize", "transcribe", "align"}
