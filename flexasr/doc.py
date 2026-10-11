"""The intermediate format between stages (``flexasr-doc/1``).

Every stage reads and writes a :class:`Doc`, so stages can run separately, be cached, be re-run with
another provider, or be done by an external tool and fed back in (dev/RESHAPE-2026-10.md §3.0). It is
plain data: JSON in, JSON out. Times are seconds from the start of the recording.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA = "flexasr-doc/1"

# What a word is, for the verbatim encoding (§3.3b). "word" is an ordinary token; the others become
# TEITOK's spoken elements in the writer.
WORD_KINDS = ("word", "punct", "filler", "truncated", "repetition", "reformulation", "unclear", "event")


@dataclass
class Word:
    text: str
    start: Optional[float] = None
    end: Optional[float] = None
    conf: Optional[float] = None
    kind: str = "word"
    orig: Optional[str] = None          # the engine's own spelling, when the encoding changed it
    speaker: Optional[str] = None
    space_after: bool = True            # False: the next token follows without a space ("Bonjour" ".")


@dataclass
class Utterance:
    id: str
    start: Optional[float]
    end: Optional[float]
    speaker: Optional[str] = None
    words: list[Word] = field(default_factory=list)
    text: Optional[str] = None          # engine text before word segmentation (kept for reference)
    overlap: bool = False               # overlaps speech of another speaker (marked for review)


@dataclass
class Turn:
    speaker: str
    start: float
    end: float


@dataclass
class Pause:
    start: float
    end: float
    speaker: Optional[str] = None


@dataclass
class Speaker:
    id: str                              # stable id in the output (spk1, …)
    label: str                           # the diarization label (SPEAKER_00, …)
    name: Optional[str] = None
    role: Optional[str] = None           # e.g. interviewer; roles can be untokenized
    tokenize: bool = True


@dataclass
class Provenance:
    stage: str
    provider: str
    model: Optional[str] = None          # catalog id
    source: Optional[str] = None         # e.g. hf:Systran/faster-whisper-tiny
    revision: Optional[str] = None
    licence: Optional[str] = None
    restricted: list[str] = field(default_factory=list)   # e.g. ["noncommercial"]
    settings: dict[str, Any] = field(default_factory=dict)
    version: Optional[str] = None        # provider library version


@dataclass
class Audio:
    path: str
    duration: Optional[float] = None
    sample_rate: Optional[int] = None


@dataclass
class Doc:
    audio: Audio
    language: Optional[str] = None       # ISO 639-3
    mode: str = "clean"                  # clean | verbatim
    turns: list[Turn] = field(default_factory=list)            # full diarization (may overlap)
    turns_exclusive: list[Turn] = field(default_factory=list)  # one speaker at a time
    speakers: list[Speaker] = field(default_factory=list)
    utterances: list[Utterance] = field(default_factory=list)
    pauses: list[Pause] = field(default_factory=list)
    provenance: list[Provenance] = field(default_factory=list)
    done: list[str] = field(default_factory=list)              # stages that ran, in order
    schema: str = SCHEMA

    # -- serialisation ---------------------------------------------------------------------------
    def to_json(self, indent: Optional[int] = 1) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=indent)

    @classmethod
    def from_json(cls, text: str) -> "Doc":
        d = json.loads(text)
        if d.get("schema") != SCHEMA:
            raise ValueError(f"not a {SCHEMA} document (schema: {d.get('schema')!r})")
        return cls(
            audio=Audio(**d["audio"]),
            language=d.get("language"),
            mode=d.get("mode", "clean"),
            turns=[Turn(**t) for t in d.get("turns", [])],
            turns_exclusive=[Turn(**t) for t in d.get("turns_exclusive", [])],
            speakers=[Speaker(**s) for s in d.get("speakers", [])],
            utterances=[
                Utterance(**{**u, "words": [Word(**w) for w in u.get("words", [])]})
                for u in d.get("utterances", [])
            ],
            pauses=[Pause(**p) for p in d.get("pauses", [])],
            provenance=[Provenance(**p) for p in d.get("provenance", [])],
            done=list(d.get("done", [])),
        )

    # -- helpers ---------------------------------------------------------------------------------
    def words(self):
        for u in self.utterances:
            yield from u.words

    def speaker(self, sid: Optional[str]) -> Optional[Speaker]:
        return next((s for s in self.speakers if s.id == sid), None)
