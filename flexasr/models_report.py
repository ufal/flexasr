"""The catalog as data, for front-ends (the TEITOK module): every entry with whether it can be used
here and why not, and what the router would choose per task (``flexasr models --json``)."""

from __future__ import annotations

from typing import Any, Optional

from . import catalog, langs
from .hardware import detect
from .registry import all_providers

TASKS = ("diarize", "transcribe", "align")


def _access(e: catalog.Entry, why: list[str]) -> list[str]:
    """Gated models: whether this machine has access (otherwise the router would skip them)."""
    if not e.gated or why:
        return why
    from .access import check

    acc = check(e)
    return why if acc.ok else why + [acc.reason]


def _entry(e: catalog.Entry, why: list[str], device: Optional[str]) -> dict[str, Any]:
    why = _access(e, why)
    return {"id": e.id, "task": e.task, "provider": e.provider, "source": e.source, "licence": e.licence,
            "restricted": e.restricted, "licence_note": e.licence_note, "gated": e.gated,
            "languages": e.languages, "modes": e.modes, "priority": e.priority, "note": e.note,
            "usable": not why, "why_not": why, "device": device if not why else None}


def _choice(task: str, lang: Optional[str], mode: str, allow: bool, entries) -> dict[str, Any]:
    try:
        ch = catalog.choose(task, lang, mode, allow_restricted=allow, entries=entries)
        return {"id": ch.entry.id if ch.entry else ch.provider.spec.name, "device": ch.device, "notes": ch.notes}
    except catalog.NoChoice as e:
        return {"id": None, "error": str(e)}


def report(lang: Optional[str] = None, mode: str = "clean", allow_restricted: bool = False,
           task: Optional[str] = None) -> dict[str, Any]:
    lang = langs.norm(lang)
    hw, entries, providers = detect(), catalog.load(), all_providers()
    tasks = [task] if task else list(TASKS)
    out: dict[str, Any] = {"language": lang, "language_name": langs.name(lang), "mode": mode,
                           "allow_restricted": allow_restricted, "devices": list(hw.devices),
                           "entries": [], "choice": {}}
    for t in tasks:
        for _, e, _, av, why in catalog.candidates(t, lang, mode, hw, allow_restricted, entries, providers):
            out["entries"].append(_entry(e, list(why), av.device if av else None))
        out["choice"][t] = _choice(t, lang, mode, allow_restricted, entries)
    return out
