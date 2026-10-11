"""Stage contracts and provider capabilities (dev/RESHAPE-2026-10.md §3.0).

A *provider* fulfils one or more stage contracts. The pipeline only knows the contracts below; it never
names a model. A provider declares what it can do in a :class:`ProviderSpec`; the router (catalog.py)
chooses among the providers that are usable on this machine.

Providers are found in ``flexasr.providers.*`` (modules with a ``PROVIDER`` attribute) and in the entry
point group ``flexasr.providers`` — so a provider can be a separate package.
"""

from __future__ import annotations

import importlib.util
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:  # pragma: no cover
    import numpy as np

    from ..catalog import Entry
    from ..doc import Doc, Turn, Utterance

STAGES = ("diarize", "transcribe", "align")


@dataclass(frozen=True)
class ProviderSpec:
    name: str                                   # e.g. "faster-whisper"
    family: str                                 # model family it can run, e.g. "whisper-ct2"
    tasks: tuple[str, ...]                      # subset of STAGES
    languages: tuple[str, ...] = ("*",)         # ISO 639-3, "*" = any (the model may narrow it)
    modes: tuple[str, ...] = ("clean",)         # clean | verbatim (what the provider itself can do)
    timestamps: str = "none"                    # transcribe: word | segment | none
    devices: tuple[str, ...] = ("cpu",)         # where it can run
    requires: tuple[str, ...] = ()              # importable Python modules it needs
    needs_model: bool = True                    # False: works without a catalog entry
    needs_token: bool = False                   # e.g. gated Hugging Face models
    description: str = ""


@dataclass
class Availability:
    usable: bool
    reason: str = ""
    device: Optional[str] = None


def availability(spec: ProviderSpec, hardware) -> Availability:
    """Can this provider run here, and on which device? (``reason`` says why not.)"""
    missing = [m for m in spec.requires if importlib.util.find_spec(m) is None]
    if missing:
        return Availability(False, "missing Python module(s): " + ", ".join(missing))
    device = hardware.best(spec.devices)
    if device is None:
        return Availability(False, "needs " + " or ".join(d.upper() for d in spec.devices))
    return Availability(True, "", device)


@dataclass
class Context:
    """What a provider gets: its model entry (if any), device, options, and the run's settings."""

    device: str
    entry: Optional["Entry"] = None
    options: dict[str, Any] = field(default_factory=dict)
    language: Optional[str] = None
    mode: str = "clean"
    token: Optional[str] = None


class Provider:
    spec: ProviderSpec

    def __init__(self, ctx: Context):
        self.ctx = ctx

    # Provenance for the layer this provider produced (filled into Doc.provenance by the pipeline).
    def version(self) -> Optional[str]:
        return None


class Diarizer(Provider):
    def diarize(self, audio: "np.ndarray", sr: int, doc: "Doc",
                num_speakers: Optional[int] = None,
                min_speakers: Optional[int] = None,
                max_speakers: Optional[int] = None) -> tuple[list["Turn"], list["Turn"]]:
        """Return (full turns, which may overlap; exclusive turns, one speaker at a time)."""
        raise NotImplementedError


class Transcriber(Provider):
    def transcribe(self, audio: "np.ndarray", sr: int, doc: "Doc") -> list["Utterance"]:
        """Utterances with words. Word times may be None when ``spec.timestamps`` is not "word";
        the align stage then fills them in."""
        raise NotImplementedError


class Aligner(Provider):
    def align(self, audio: "np.ndarray", sr: int, doc: "Doc") -> None:
        """Set (or improve) word start/end times in ``doc`` in place, keeping the words."""
        raise NotImplementedError


CONTRACTS = {"diarize": Diarizer, "transcribe": Transcriber, "align": Aligner}
