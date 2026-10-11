"""The routing catalog: which model does what, for which language (dev/RESHAPE-2026-10.md §3.2).

flexasr hosts no models (§3.5b): an entry records only where a model comes from (source, pinned
revision, checksums), its licence and restrictions, and what it can do. Entries come from, in order
(later ones override earlier ones by id): flexasr's own built-in providers (``catalog/builtins.json``),
the shared models repository (models_repo.py; when unreachable: the cached copy, else the bundled
``catalog/registry-snapshot.json``), then ``~/.flexasr/catalog/*.json``.

Routing (:func:`choose`) picks, per stage, the best entry whose provider is usable on this machine:
language-specific entries before "*", verbatim entries first when verbatim is asked, restricted
(e.g. non-commercial) entries only when allowed, then by ``priority``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from . import langs, models_repo
from .hardware import Hardware, detect
from .providers.base import Availability, availability
from .registry import Registered, all_providers

from .home import user_dir  # noqa: F401  (re-exported)

BUNDLED = Path(__file__).parent / "catalog"


@dataclass
class Entry:
    id: str
    task: str                                 # diarize | transcribe | align
    provider: str                             # provider name that runs it
    source: Optional[str] = None              # hf:<repo> | url:<…> | None (provider needs no model)
    revision: Optional[str] = None            # pinned commit; None = not pinned yet
    sha256: dict[str, str] = field(default_factory=dict)
    licence: Optional[str] = None
    licence_verified: bool = False
    restricted: list[str] = field(default_factory=list)   # noncommercial, sharealike, …
    licence_note: str = ""                    # shown before the first download (e.g. training-data terms)
    gated: bool = False
    languages: list[str] = field(default_factory=lambda: ["*"])
    modes: list[str] = field(default_factory=lambda: ["clean"])
    timestamps: Optional[str] = None
    devices: Optional[list[str]] = None       # narrows the provider's devices (e.g. VRAM needs)
    priority: int = 0
    options: dict[str, Any] = field(default_factory=dict)  # provider options for this model
    scores: list[dict[str, Any]] = field(default_factory=list)
    note: str = ""

    def covers(self, lang: Optional[str]) -> bool:
        return "*" in self.languages or (lang is not None and lang in self.languages)


def _models(data: Any) -> list[dict[str, Any]]:
    return data.get("models", []) if isinstance(data, dict) else list(data)


def _read(f: Path) -> list[dict[str, Any]]:
    return _models(json.loads(f.read_text(encoding="utf-8")))


def _shared(use_remote: bool) -> list[dict[str, Any]]:
    """Entries from the shared models repository, or the bundled snapshot of it."""
    got = models_repo.asr_entries() if use_remote else None
    return got if got is not None else _read(BUNDLED / "registry-snapshot.json")


def _entry(e: dict[str, Any]) -> Entry:
    e = dict(e)
    e["languages"] = [x if x == "*" else langs.norm(x) for x in e.get("languages", ["*"])]
    known = Entry.__dataclass_fields__
    return Entry(**{k: v for k, v in e.items() if k in known})


def load(extra_dirs: Optional[list[Path]] = None, use_remote: bool = True) -> dict[str, Entry]:
    layers = [_read(BUNDLED / "builtins.json"), _shared(use_remote)]
    for d in [user_dir() / "catalog"] + list(extra_dirs or []):
        if d.is_dir():
            layers += [_read(f) for f in sorted(d.glob("*.json"))]
    return {e["id"]: _entry(e) for layer in layers for e in layer}


@dataclass
class Choice:
    task: str
    provider: Registered
    entry: Optional[Entry]
    device: str
    notes: list[str] = field(default_factory=list)   # e.g. "no verbatim model: output normalized"


class NoChoice(RuntimeError):
    pass


def candidates(task: str, lang: Optional[str], mode: str, hw: Hardware, allow_restricted: bool,
               entries: dict[str, Entry], providers: dict[str, Registered]):
    """All entries for ``task`` with whether they can be used here, best first."""
    out = []
    for e in entries.values():
        if e.task != task:
            continue
        why = []
        reg = providers.get(e.provider)
        av: Optional[Availability] = None
        if reg is None:
            why.append(f"provider {e.provider!r} not installed")
        elif reg.error:
            why.append(reg.error)
        else:
            av = availability(reg.spec, hw)
            if av.usable and e.devices:
                dev = hw.best(tuple(d for d in reg.spec.devices if d in e.devices))
                av = Availability(dev is not None, "" if dev else "needs " + "/".join(e.devices), dev)
            if not av.usable:
                why.append(av.reason)
        if not e.covers(lang):
            why.append(f"does not cover language {lang}")
        if e.restricted and not allow_restricted:
            why.append("restricted licence (" + ", ".join(e.restricted) + "); allow with --allow-restricted")
        rank = (
            1 if (task != "transcribe" or mode in e.modes) else 0,   # wanted mode first (transcription only)
            1 if lang and lang in e.languages else 0,  # language-specific before "*"
            e.priority,
        )
        out.append((rank, e, reg, av, why))
    out.sort(key=lambda t: t[0], reverse=True)
    return out


def choose(task: str, lang: Optional[str], mode: str = "clean", *, hw: Optional[Hardware] = None,
           allow_restricted: bool = False, provider: Optional[str] = None, model: Optional[str] = None,
           entries: Optional[dict[str, Entry]] = None) -> Choice:
    """The entry (and provider, device) to use for one stage. ``provider`` / ``model`` override."""
    hw = hw or detect()
    entries = entries if entries is not None else load()
    providers = all_providers()
    cands = candidates(task, lang, mode, hw, allow_restricted, entries, providers)
    if model:
        cands = [c for c in cands if c[1].id == model]
        if not cands:
            raise NoChoice(f"no catalog entry {model!r} for task {task}")
    if provider:
        cands = [c for c in cands if c[1].provider == provider]
        if not cands:
            raise NoChoice(f"no catalog entry for provider {provider!r} and task {task}")
    for i, (rank, e, reg, av, why) in enumerate(cands):
        if why:
            continue
        if e.gated:                       # checked only for the entry about to be chosen (may go online)
            from .access import check

            acc = check(e)
            if not acc.ok:
                why.append(acc.reason)
                continue
        notes = []
        if task == "transcribe" and mode == "verbatim" and "verbatim" not in e.modes:
            notes.append(f"no usable verbatim {task} model for {lang or 'this language'}: "
                         f"{e.id} produces normalized text (fillers may be dropped)")
        skipped = [f"{x.id} ({'; '.join(w)})" for _, x, _, _, w in cands[:i] if w and x.priority > e.priority]
        if skipped:
            notes.append("better entries skipped: " + ", ".join(skipped))
        return Choice(task, reg, e, av.device, notes)
    lines = [f"  {e.id}: {'; '.join(why) or 'not reached'}" for _, e, _, _, why in cands] or ["  (no entries)"]
    raise NoChoice(f"no usable {task} model for language {lang}, mode {mode}:\n" + "\n".join(lines))
