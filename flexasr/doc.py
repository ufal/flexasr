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
    src: Optional[int] = None           # transcript input: the element this word came from (its index among the file's start tags)
    timing: Optional[str] = None        # transcript input: "given" (times were in the file), "estimated" (from the text, not the audio)


@dataclass
class Utterance:
    id: str
    start: Optional[float]
    end: Optional[float]
    speaker: Optional[str] = None
    words: list[Word] = field(default_factory=list)
    text: Optional[str] = None          # engine text before word segmentation (kept for reference)
    overlap: bool = False               # overlaps speech of another speaker (marked for review)
    src: Optional[int] = None           # transcript input: the <u> this came from (None: tokens outside any <u>)
    parent: Optional[int] = None        # transcript input, tokens outside any <u>: the element they are in
    parent_tag: Optional[str] = None    # its name (a <p> is a transcriber's utterance boundary)
    new: bool = False                   # transcript input: a <u> the run adds (written around its tokens)
    review: Optional[str] = None        # why a person should check it (e.g. "speaker": the speaker is uncertain)


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
class Transcript:
    """An existing transcript the run adds times to (instead of producing fresh output)."""

    path: str
    sha256: str                          # of the file as read: write-back refuses a file that changed since


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
    run: dict[str, Any] = field(default_factory=dict)          # how it was run: settings, date (for the header)
    transcript: Optional[Transcript] = None                    # transcript input: the file times are added to
    hypothesis: list[Utterance] = field(default_factory=list)  # transcript input: the ASR output, used for its times only
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
            utterances=[_utterance(u) for u in d.get("utterances", [])],
            pauses=[Pause(**p) for p in d.get("pauses", [])],
            provenance=[Provenance(**p) for p in d.get("provenance", [])],
            done=list(d.get("done", [])),
            run=dict(d.get("run", {})),
            transcript=Transcript(**d["transcript"]) if d.get("transcript") else None,
            hypothesis=[_utterance(u) for u in d.get("hypothesis", [])],
        )

    # -- helpers ---------------------------------------------------------------------------------
    def words(self):
        for u in self.utterances:
            yield from u.words

    def speaker(self, sid: Optional[str]) -> Optional[Speaker]:
        return next((s for s in self.speakers if s.id == sid), None)


def _utterance(u: dict) -> Utterance:
    return Utterance(**{**u, "words": [Word(**w) for w in u.get("words", [])]})
