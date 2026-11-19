"""The stages, one small function each, registered by name.

A stage takes the Doc, the run settings and a :class:`Run` (audio, progress callback, provider
factory) and changes the Doc. Adding a stage is adding a function here and an entry in ``STAGES``;
the pipeline loop never grows.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import TYPE_CHECKING, Callable, Optional

from .assign import assign as assign_speakers
from .assign_transcript import assign_transcript, needs as needs_speakers, summary as assign_summary
from .disfluency import encode as encode_disfluencies
from . import speech as speech_regions
from .match import match as match_transcript
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
    if doc.transcript and not needs_speakers(doc):
        r.progress("diarize: the transcript has its utterances and speakers")
        return
    persons = (doc.run.get("transcript_read") or {}).get("persons") or []
    if doc.transcript and len(persons) >= 2 and not (s.num_speakers or s.min_speakers or s.max_speakers):
        s = replace(s, num_speakers=len(persons))            # the header names the speakers: that many
        r.progress(f"diarize: {len(persons)} speakers, as in the header's listPerson")
    prov, rec = r.provider("diarize", s, doc)
    r.progress(f"diarize: {rec.provider} ({rec.model or '-'}) on {rec.settings['device']}")
    doc.turns, doc.turns_exclusive = prov.diarize(r.wav, r.sr, doc, s.num_speakers, s.min_speakers,
                                                  s.max_speakers)
    doc.provenance.append(rec)


def transcribe(doc: "Doc", s: "Settings", r: Run) -> None:
    prov, rec = r.provider("transcribe", s, doc)
    r.progress(f"transcribe: {rec.provider} ({rec.model}) on {rec.settings['device']}")
    if doc.transcript:                        # an existing transcript: the ASR words are only used for their times
        doc.hypothesis = prov.transcribe(r.wav, r.sr, doc)
    else:
        doc.utterances = prov.transcribe(r.wav, r.sr, doc)
    doc.provenance.append(rec)


def match(doc: "Doc", s: "Settings", r: Run) -> None:
    if not doc.transcript:
        raise RuntimeError("match needs a transcript as input (flexasr run FILE.xml)")
    if doc.turns:
        speech, where = speech_regions.from_turns(doc.turns), "the diarization"
    else:
        speech, where = speech_regions.from_audio(r.wav, r.sr), "the audio's energy"
    if speech:
        r.progress(f"match: {sum(b - a for a, b in speech):.0f} s of speech found in {where}; estimated times go there")
    rep = match_transcript(doc, speech=speech or None,
                           **{k: v for k, v in s.options.get("match", {}).items() if k == "margin"})
    doc.run["match"] = asdict(rep)
    r.progress(rep.summary())
    from .readers.teitok import untokenized_note

    note = untokenized_note(doc)
    if note:
        r.progress(f"match: {note}")


def align(doc: "Doc", s: "Settings", r: Run) -> None:
    if doc.transcript and "align" not in s.providers and "align" not in s.models:
        r.progress("align: the ASR word times are kept (give --model align=… to align the transcript instead)")
        return
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
    if doc.transcript:
        if not needs_speakers(doc):
            return
        rep = assign_transcript(doc, s.speaker_map, s.split_gap, snap=s.snap_boundaries, snap_shift=s.snap_shift)
        doc.run["assign"] = rep
        r.progress(assign_summary(doc, rep))
        return
    if not (doc.turns or doc.turns_exclusive):
        raise RuntimeError("assign needs diarization turns (run the diarize stage)")
    assign_speakers(doc, s.speaker_map, s.untokenized_roles, s.split_gap, snap=s.snap_boundaries, snap_shift=s.snap_shift,
                    interviewer=s.interviewer)
    r.progress(f"assign: {len(doc.speakers)} speaker(s), {len(doc.utterances)} utterance(s)")


def encode(doc: "Doc", s: "Settings", r: Run) -> None:
    if doc.mode != "verbatim":
        return
    encode_disfluencies(doc, doc.language, s.pause_min)
    n = sum(1 for w in doc.words() if w.kind not in ("word", "punct"))
    r.progress(f"encode: {n} disfluency mark(s), {len(doc.pauses)} pause(s)")


STAGES: dict[str, Callable] = {
    "diarize": diarize, "transcribe": transcribe, "match": match, "align": align,
    "tokens": tokens, "assign": assign, "encode": encode,
}
NEEDS_AUDIO = {"diarize", "transcribe", "match", "align"}     # match: where the speech is, for estimates
