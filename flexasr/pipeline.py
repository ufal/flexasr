"""The pipeline: stages over a Doc, each model stage routed through the catalog.

    diarize → transcribe → align → assign → encode (verbatim only) → write

With an existing transcript as input (``readers/teitok.py``) the transcript wins and only gets times:

    [diarize] → transcribe (ASR words kept apart) → match → align (only when asked) → [assign] → write-back

diarize and assign run only for tokens without utterances or speakers.

A stage reads and writes the Doc only, so any stage can be re-run, resumed from a saved Doc, or done
outside flexasr (dev/RESHAPE-2026-10.md §3.0). The pipeline never names a model: ``catalog.choose``
does, per language, mode and hardware, unless the user overrides a provider or model per stage.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from . import audio as audio_io
from . import catalog, langs
from .stages import NEEDS_AUDIO, STAGES, Run
from .doc import Audio, Doc, Provenance
from .hardware import detect
from .home import load_config  # noqa: F401  (re-exported)
from .providers.base import CONTRACTS, Context

log = logging.getLogger("flexasr")

ALL_STAGES = ("diarize", "transcribe", "align", "tokens", "assign", "encode")
# An existing transcript: times, and utterances and speakers only where it has none (diarize and assign skip
# themselves otherwise). dev/REALIGN.md
TRANSCRIPT_STAGES = ("diarize", "transcribe", "match", "align", "assign")


@dataclass
class Settings:
    language: Optional[str] = None
    mode: str = "clean"                                   # clean | verbatim
    allow_restricted: bool = False
    providers: dict[str, str] = field(default_factory=dict)   # stage → provider name
    models: dict[str, str] = field(default_factory=dict)      # stage → catalog id
    options: dict[str, dict[str, Any]] = field(default_factory=dict)  # stage → provider options
    num_speakers: Optional[int] = None
    min_speakers: Optional[int] = None
    max_speakers: Optional[int] = None
    speaker_map: dict[str, dict] = field(default_factory=dict)
    untokenized_roles: tuple[str, ...] = ()
    split_gap: float = 2.0
    snap_boundaries: bool = True                          # speaker changes to the nearest pause / sentence end (snap.py)
    snap_shift: float = 1.5
    interviewer: Optional[str] = None                     # first | second | least | most: who is the interviewer
    pause_min: float = 0.3
    token: Optional[str] = None
    keep_dir: Optional[Path] = None                       # save the Doc after every stage

    def hf_token(self) -> Optional[str]:
        return self.token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")


def _provider(stage: str, s: Settings, doc: Doc, progress: Callable[[str], None] = log.info):
    """Choose and instantiate the provider for a model stage."""
    ch = catalog.choose(stage, doc.language, s.mode, allow_restricted=s.allow_restricted,
                        provider=s.providers.get(stage), model=s.models.get(stage),
                        word_times=stage == "transcribe" and doc.transcript is not None)
    for n in ch.notes:
        log.warning(n)
    e = ch.entry
    if e and e.restricted:
        log.warning("using %s under a restricted licence (%s: %s)", e.id, e.licence, ", ".join(e.restricted))
    if e and (e.source or "").startswith("hf:"):
        from .access import download_notice

        note = download_notice(e)
        if note:
            progress(note)
    cls = ch.provider.load()
    if not issubclass(cls, CONTRACTS[stage]):
        raise TypeError(f"provider {cls.spec.name} does not implement the {stage} contract")
    opts = {**(e.options if e else {}), **s.options.get(stage, {})}
    prov = cls(Context(device=ch.device, entry=e, options=opts, language=doc.language, mode=s.mode,
                       token=s.hf_token()))
    rec = Provenance(stage=stage, provider=cls.spec.name, model=e.id if e else None,
                     source=e.source if e else None, revision=e.revision if e else None,
                     licence=e.licence if e else None, restricted=list(e.restricted) if e else [],
                     settings={"device": ch.device, **({"options": opts} if opts else {})})
    try:
        rec.version = prov.version()
    except Exception:
        pass
    return prov, rec


def _run_record(s: Settings) -> dict:
    """The settings that shape the output, kept in the document so the header can state them."""
    import datetime

    rec = {"date": datetime.date.today().isoformat(), "mode": s.mode, "allow_restricted": s.allow_restricted,
           "split_gap": s.split_gap, "pause_min": s.pause_min,
           "snap_shift": s.snap_shift if s.snap_boundaries else 0}
    if s.num_speakers or s.min_speakers or s.max_speakers:
        rec["speakers_requested"] = {k: v for k, v in (("n", s.num_speakers), ("min", s.min_speakers),
                                                       ("max", s.max_speakers)) if v}
    if s.untokenized_roles:
        rec["untokenized_roles"] = list(s.untokenized_roles)
    if s.interviewer:
        rec["interviewer"] = s.interviewer
    if s.providers or s.models:
        rec["overrides"] = {"providers": dict(s.providers), "models": dict(s.models)}
    return rec


def new_doc(path: str | Path, s: Settings) -> Doc:
    return Doc(audio=Audio(path=str(path)), language=langs.norm(s.language), mode=s.mode)


def run(path: str | Path, s: Settings, stages: Optional[tuple[str, ...]] = None, doc: Optional[Doc] = None,
        progress: Callable[[str], None] = lambda m: log.info(m)) -> Doc:
    from .cache import setup as setup_cache

    mdir = setup_cache(load_config())        # before any model library is imported
    from .quiet import quiet

    quiet()                                  # the libraries' progress bars and repeated warnings stay out of the log
    doc = doc or new_doc(path, s)
    if stages is None:
        stages = TRANSCRIPT_STAGES if doc.transcript else ALL_STAGES
    unknown = [st for st in stages if st not in STAGES]
    if unknown:
        raise ValueError(f"unknown stage(s) {', '.join(unknown)} (stages: {', '.join(STAGES)})")
    if s.language:
        doc.language = langs.norm(s.language)
    doc.mode = s.mode
    doc.run.update(_run_record(s))
    wav = sr = None
    if NEEDS_AUDIO & set(stages):
        wav, sr = audio_io.load(doc.audio.path)
        doc.audio.duration, doc.audio.sample_rate = round(len(wav) / sr, 3), sr
    progress(f"hardware: {', '.join(detect().devices)}" + (f"; models in {mdir}" if mdir else ""))
    r = Run(wav=wav, sr=sr, progress=progress, provider=lambda st, ss, d: _provider(st, ss, d, progress))
    for st in stages:
        STAGES[st](doc, s, r)
        doc.done.append(st)
        if s.keep_dir:
            s.keep_dir.mkdir(parents=True, exist_ok=True)
            (s.keep_dir / f"{Path(doc.audio.path).stem}.{st}.json").write_text(doc.to_json(), encoding="utf-8")
    return doc
