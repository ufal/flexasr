"""The pipeline: stages over a Doc, each model stage routed through the catalog.

    diarize → transcribe → align → assign → encode (verbatim only) → write

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
    pause_min: float = 0.3
    token: Optional[str] = None
    keep_dir: Optional[Path] = None                       # save the Doc after every stage

    def hf_token(self) -> Optional[str]:
        return self.token or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")


def _provider(stage: str, s: Settings, doc: Doc, progress: Callable[[str], None] = log.info):
    """Choose and instantiate the provider for a model stage."""
    ch = catalog.choose(stage, doc.language, s.mode, allow_restricted=s.allow_restricted,
                        provider=s.providers.get(stage), model=s.models.get(stage))
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


def new_doc(path: str | Path, s: Settings) -> Doc:
    return Doc(audio=Audio(path=str(path)), language=langs.norm(s.language), mode=s.mode)


def run(path: str | Path, s: Settings, stages: tuple[str, ...] = ALL_STAGES, doc: Optional[Doc] = None,
        progress: Callable[[str], None] = lambda m: log.info(m)) -> Doc:
    from .cache import setup as setup_cache

    mdir = setup_cache(load_config())        # before any model library is imported
    unknown = [st for st in stages if st not in STAGES]
    if unknown:
        raise ValueError(f"unknown stage(s) {', '.join(unknown)} (stages: {', '.join(ALL_STAGES)})")
    doc = doc or new_doc(path, s)
    if s.language:
        doc.language = langs.norm(s.language)
    doc.mode = s.mode
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
