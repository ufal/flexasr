"""Punctuation split off as separate tokens without times.

Ecosystem convention (as for OCR, where split-off punctuation gets no bbox): the word keeps its times,
the punctuation becomes its own ``<tok>`` without ``start``/``end`` — "not ideal, but prevents guessing".
Leading and trailing punctuation is split; apostrophes and hyphens inside a word ("qu'est-ce"), a
trailing hyphen (a truncation, see disfluency.py) and numbers ("3.5", "1,5") stay as they are.
"""

from __future__ import annotations

import re
import unicodedata

from .doc import Doc, Word

_EVENT = re.compile(r"^[\[\(<].+[\]\)>]$")     # [laughter], (rires), <laugh>: stays whole

_KEEP_TRAILING = {"-", "‐", "–"}          # truncation marks, not punctuation


def _is_punct(ch: str) -> bool:
    return unicodedata.category(ch).startswith("P") or ch in "…"


def _split(text: str) -> tuple[list[str], str, list[str]]:
    """(leading punctuation marks, core, trailing punctuation marks); runs like "?!" or "..." stay one."""
    i, j = 0, len(text)
    while i < j and _is_punct(text[i]) and text[i] not in "'’-":
        i += 1
    while j > i and _is_punct(text[j - 1]) and text[j - 1] not in _KEEP_TRAILING and text[j - 1] not in "'’":
        j -= 1
    core = text[i:j]
    if not core:                           # the whole word is punctuation: leave it a single token
        return [], text, []
    lead = [text[:i]] if i else []
    trail = [text[j:]] if j < len(text) else []
    return lead, core, trail


def split_punctuation(doc: Doc) -> int:
    """Split punctuation off every word, in place; returns the number of punctuation tokens added."""
    added = 0
    for u in doc.utterances:
        out: list[Word] = []
        for w in u.words:
            if w.kind == "event" or _EVENT.match(w.text.strip()):
                out.append(w)
                continue
            lead, core, trail = _split(w.text)
            if not lead and not trail:
                if core and all(_is_punct(c) for c in core):
                    w.kind = "punct"
                    w.start = w.end = None
                out.append(w)
                continue
            # no space is introduced: "«Bonjour," stays «Bonjour, in the text
            for p in lead:
                out.append(Word(text=p, kind="punct", speaker=w.speaker, space_after=False))
            w.text = core                      # (no orig: word + punctuation tokens give it back)
            after = w.space_after
            out.append(w)
            for i, p in enumerate(trail):
                out[-1].space_after = False
                out.append(Word(text=p, kind="punct", speaker=w.speaker, space_after=after))
            added += len(lead) + len(trail)
        u.words = out
    return added
