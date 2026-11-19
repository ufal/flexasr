"""Times from the text, where the audio gave none: words share out a stretch of time by their vowel groups.

The same reckoning as spoken-edit's (teitok_modules/spoken-edit-estimate.php): a vowel group (a run of
vowels, so a diphthong counts once) is about one syllable, and syllables follow time better than letters
or words do. Punctuation stands for a pause whose length the text does not give: a sentence end about a
syllable and a half, a comma a little over half. Always an estimate: the words get ``timing="estimated"``.
"""

from __future__ import annotations

import bisect
import re
import unicodedata
from typing import Optional, Sequence

from .doc import Word

_VOWELS = re.compile(r"[aeiouyæœøå]+")
_SENTENCE_END = {".", "?", "!", "…", "...", "。"}
_CLAUSE = {",", ";", ":", "—", "–"}


def _fold(text: str) -> str:
    t = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in t if not unicodedata.category(c).startswith("M"))


def vowel_weight(text: str) -> int:
    """The vowel groups of a word: 0 for something that is not a word, at least 1 for a word."""
    t = _fold(text)
    if not any(c.isalpha() for c in t):
        return 0
    return max(1, len(_VOWELS.findall(t)))


def punct_weight(text: str) -> float:
    t = text.strip()
    if t in _SENTENCE_END:
        return 1.5
    if t in _CLAUSE:
        return 0.6
    return 0.0


MIN_SPEECH_SHARE = 0.05     # less speech than this in a stretch: the detector missed it, spread over the whole stretch


def _clip(speech: Sequence[tuple[float, float]], start: float, end: float) -> list[tuple[float, float]]:
    i = bisect.bisect_right([b for _, b in speech], start)
    out = []
    for a, b in speech[i:]:
        if a >= end:
            break
        out.append((max(a, start), min(b, end)))
    return [(a, b) for a, b in out if b > a]


def _clock(segs: list[tuple[float, float]]):
    """Speaking time (seconds into the speech of the stretch) → time in the recording. A start at the end of one
    stretch of speech goes to the start of the next; an end stays where the speech stopped."""
    cum = [0.0]
    for a, b in segs:
        cum.append(cum[-1] + (b - a))

    def at(x: float, is_start: bool) -> float:
        k = bisect.bisect_right(cum, x) - 1 if is_start else bisect.bisect_left(cum, x) - 1
        k = min(max(k, 0), len(segs) - 1)
        return segs[k][0] + (x - cum[k])

    return cum[-1], at


def spread(words: Sequence[Word], spoken: Sequence[bool], start: float, end: float,
           speech: Optional[Sequence[tuple[float, float]]] = None) -> int:
    """Give the spoken words of a run times between `start` and `end`, by weight; punctuation in the run takes
    its share as a pause but gets no times. With `speech` (sorted, merged stretches where someone speaks), the
    words go into the speech only and the silences between stay silences. Returns the number of words timed
    (0 when the run has no room)."""
    weights = [vowel_weight(w.text) if sp else punct_weight(w.text) for w, sp in zip(words, spoken)]
    total = sum(weights)
    if end <= start or total <= 0:
        return 0
    segs = _clip(speech, start, end) if speech else []
    if sum(b - a for a, b in segs) < MIN_SPEECH_SHARE * (end - start):
        segs = [(start, end)]
    length, at = _clock(segs)
    t, n = 0.0, 0
    for w, sp, wt in zip(words, spoken, weights):
        d = length * wt / total
        if sp:
            w.start, w.end, w.timing = round(at(t, True), 3), round(at(t + d, False), 3), "estimated"
            n += 1
        t += d
    return n
