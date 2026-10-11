"""Verbatim encoding: which words are fillers, truncations, repetitions, events; where pauses are.

The writer turns these kinds into TEITOK's spoken elements (dev/RESHAPE-2026-10.md §3.3b):
filler → ``<vocal><desc>…</desc></vocal>``, truncated / repetition / reformulation →
``<del reason="…">``, event → ``<incident>``, pauses → ``<pause type dur>``.
Only applied in verbatim mode; the engine's own spelling is kept in ``Word.orig`` when changed.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .doc import Doc, Pause

# Filled pauses / hesitations per language (ISO 639-3); lowercase, without punctuation. Extend per
# project. Only non-lexical items: words like French "ben" or English "like" stay words.
FILLERS: dict[str, set[str]] = {
    "fra": {"euh", "heu", "euhm", "hum", "hm", "hmm", "mh", "mmh", "mm", "bah", "ah", "oh", "hein"},
    "eng": {"uh", "um", "uhm", "er", "erm", "hm", "hmm", "mm", "mhm", "ah"},
    "deu": {"äh", "ähm", "öh", "hm", "hmm", "mhm"},
    "nld": {"uh", "uhm", "eh", "ehm", "hm", "hmm"},
    "spa": {"eh", "em", "ehm", "mm", "hm"},
    "por": {"hum", "ahn", "eh", "uh", "hm"},
    "ita": {"ehm", "eh", "mm", "hm", "uhm"},
    "ces": {"eee", "ehm", "hm", "hmm", "ee"},
    "pol": {"yyy", "eee", "hm", "ehm"},
    "rus": {"э", "ээ", "эм", "мм", "хм"},
    "swe": {"eh", "öh", "hm", "mm"},
}
_GENERIC_FILLERS = {"hm", "hmm", "mm", "mhm"}
_EVENT = re.compile(r"^[\[\(<](.+?)[\]\)>]$")          # [laughter], (rires), <laugh>
_TRUNC = re.compile(r"^(.*\w)[-–‐]$")                  # "dé-", "pro-" (not "-ci", not "c'est-à-dire")


def _key(text: str) -> str:
    t = unicodedata.normalize("NFC", text).lower()
    return re.sub(r"[^\w\-']+", "", t)


def encode(doc: Doc, language: Optional[str] = None, pause_min: float = 0.3) -> None:
    """Classify words in place and collect pauses (gaps ≥ ``pause_min`` s inside an utterance)."""
    lang = language or doc.language
    fillers = FILLERS.get(lang or "", set()) | _GENERIC_FILLERS
    doc.pauses = []
    for u in doc.utterances:
        ws = u.words
        for w in ws:
            if w.kind == "punct":
                continue
            m = _EVENT.match(w.text.strip())
            if m:
                w.kind, w.orig, w.text = "event", w.text, m.group(1).strip()
                continue
            k = _key(w.text)
            if k in fillers:
                w.kind = "filler"
                continue
            m = _TRUNC.match(w.text.strip())
            if m:
                w.kind, w.orig, w.text = "truncated", w.text, m.group(1)
        # immediate repetitions: all but the last of a run of the same word ("je je je pense",
        # also across a comma: "je, je")
        spoken = [w for w in ws if w.kind != "punct"]
        for a, b in zip(spoken, spoken[1:]):
            if a.kind == "word" and b.kind == "word" and _key(a.text) and _key(a.text) == _key(b.text):
                a.kind = "repetition"
        timed = [w for w in ws if w.start is not None and w.end is not None]
        for a, b in zip(timed, timed[1:]):
            if b.start - a.end >= pause_min:
                doc.pauses.append(Pause(round(a.end, 3), round(b.start, 3), u.speaker))
