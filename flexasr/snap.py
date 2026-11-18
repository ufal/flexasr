"""Put speaker changes where people actually stop talking.

A diarizer says roughly when the speaker changes (a window-based one to within about a second); the words
at such a boundary, the last of one speaker and the first of the next, then often end up on the wrong side.
People change turns at pauses and sentence ends, and the transcript knows where those are. So each change
is moved to the best nearby place: the largest pause, with a bonus for a sentence end, and a small cost per
word moved, within ``max_shift`` seconds and ``max_words`` words of where the diarizer put it.
"""

from __future__ import annotations

from typing import Optional

from .doc import Word

_END = {".", "?", "!", "…", "...", "。"}
_SOFT = {",", ";", ":", "—", "–"}


def _times(words: list[Word], p: int) -> tuple[Optional[float], Optional[float]]:
    """End of the last timed word before position p, start of the first timed word from p on."""
    before = next((w.end for w in reversed(words[:p]) if w.end is not None), None)
    after = next((w.start for w in words[p:] if w.start is not None), None)
    return before, after


def _score(words: list[Word], p: int, p0: int, cost: float) -> float:
    before, after = _times(words, p)
    gap = 0.0 if before is None or after is None else min(1.5, max(0.0, after - before))
    prev = words[p - 1].text.strip()
    bonus = 0.5 if prev in _END else 0.15 if prev in _SOFT else 0.0
    moved = sum(1 for w in words[min(p, p0):max(p, p0)] if w.kind != "punct")
    return gap + bonus - cost * moved


def snap_speaker_changes(words: list[Word], max_shift: float = 1.5, max_words: int = 4,
                         cost: float = 0.1, margin: float = 0.15) -> int:
    """Move each speaker change (``Word.speaker`` differs between neighbours) to a better place. Returns how many
    changes moved. Punctuation stays with the word before it; every speaker keeps at least one word per turn."""
    n = len(words)
    moved = 0
    p_prev = 0                                        # the previous change point: never cross it
    changes = [p for p in range(1, n) if words[p].speaker != words[p - 1].speaker]
    for k, p0 in enumerate(changes):
        p_next = changes[k + 1] if k + 1 < len(changes) else n
        left, right = words[p0 - 1].speaker, words[p0].speaker
        t0 = next((w.start for w in words[p0:] if w.start is not None), None)
        best, best_score = p0, _score(words, p0, p0, cost)
        for p in range(max(p_prev + 1, p0 - max_words), min(p_next - 1, p0 + max_words) + 1):
            if p == p0 or words[p].kind == "punct":
                continue
            before, after = _times(words, p)
            if t0 is not None and after is not None and abs(after - t0) > max_shift:
                continue
            sc = _score(words, p, p0, cost)
            if sc > best_score + margin:
                best, best_score = p, sc
        if best < p0:
            for w in words[best:p0]:
                w.speaker = right
        elif best > p0:
            for w in words[p0:best]:
                w.speaker = left
        if best != p0:
            moved += 1
        p_prev = best
    return moved
