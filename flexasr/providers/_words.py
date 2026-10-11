"""Helpers for transcribers that return a flat list of timed words (no segments)."""

from __future__ import annotations

from ..doc import Utterance, Word


def utterances_from_words(words: list[Word], gap: float = 1.0) -> list[Utterance]:
    """Group timed words into utterances at silences longer than ``gap`` seconds. The assign stage
    splits them further at speaker changes; this only gives the transcript a first structure."""
    out: list[Utterance] = []
    cur: list[Word] = []

    def close():
        if cur:
            out.append(Utterance(id=f"s{len(out) + 1}", start=cur[0].start, end=cur[-1].end, words=list(cur),
                                 text=" ".join(w.text for w in cur)))
            cur.clear()

    for w in words:
        if cur and w.start is not None and cur[-1].end is not None and w.start - cur[-1].end > gap:
            close()
        cur.append(w)
    close()
    return out
