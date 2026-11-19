"""Utterances and speakers for an existing transcript that has none (dev/REALIGN.md).

The transcript wins: existing ``<u>``s stay as they are (one without ``who`` gets the speaker of most of its
words). Tokens outside any ``<u>`` get new ones, from the diarization turns, the way ``assign.py`` makes them
for ASR output — speaker per word, changes moved to pauses and sentence ends (``snap.py``), a new utterance
at each speaker change or a gap over ``split_gap`` — with the transcriber's structure as fixed boundaries:

- a new ``<u>`` never leaves the element its tokens are in (``Utterance.parent``);
- a ``<p>`` is an utterance the transcriber heard: one ``<u>`` per ``<p>``, with the speaker of most of it.
  It is split only on strong evidence, a speaker change at a sentence end with a pause of at least
  ``P_SPLIT_PAUSE``; a ``<p>`` where another speaker still has a real share is marked ``review="speaker"``.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from .assign import _overlap, _speaker_at, speakers_from_turns
from .doc import Doc, Utterance, Word
from .snap import _END, snap_speaker_changes

P_SPLIT_PAUSE = 0.5          # seconds of silence for a split inside a <p>
P_MINORITY = 0.2             # another speaker's share of a <p> that asks for review
OVERLAP_MIN = 0.2


def needs(doc: Doc) -> bool:
    """Does the transcript lack utterances or speakers anywhere?"""
    return any(u.src is None or not u.speaker for u in doc.utterances if u.words)


def _duration(w: Word) -> float:
    return max(0.0, w.end - w.start) if w.start is not None and w.end is not None else 0.0


def _majority(words: list[Word]) -> tuple[Optional[str], float]:
    """The speaker with most time (most words when untimed), and the share of the others."""
    t: dict[Optional[str], float] = defaultdict(float)
    for w in words:
        t[w.speaker] += _duration(w) or 0.01
    if not t:
        return None, 0.0
    best = max(t, key=t.get)
    total = sum(t.values())
    return best, (1 - t[best] / total) if total else 0.0


def _gap_before(words: list[Word], k: int) -> float:
    before = next((w.end for w in reversed(words[:k]) if w.end is not None), None)
    after = next((w.start for w in words[k:] if w.start is not None), None)
    return 0.0 if before is None or after is None else after - before


def _sentence_end_before(words: list[Word], k: int) -> bool:
    return k > 0 and words[k - 1].text.strip() in _END


def _cuts_free(words: list[Word], split_gap: float) -> list[int]:
    return [k for k in range(1, len(words))
            if words[k].speaker != words[k - 1].speaker or _gap_before(words, k) > split_gap]


def _cuts_p(words: list[Word]) -> list[int]:
    return [k for k in range(1, len(words)) if words[k].speaker != words[k - 1].speaker
            and _sentence_end_before(words, k) and _gap_before(words, k) >= P_SPLIT_PAUSE]


def _pieces(words: list[Word], cuts: list[int]) -> list[list[Word]]:
    edges = [0, *cuts, len(words)]
    return [words[a:b] for a, b in zip(edges, edges[1:]) if b > a]


def assign_transcript(doc: Doc, speaker_map: Optional[dict] = None, split_gap: float = 2.0, snap: bool = True,
                      snap_shift: float = 1.5) -> dict:
    """Give speakers and utterances where the transcript has none. Returns counts for the report."""
    turns = doc.turns_exclusive or doc.turns
    if not turns:
        raise RuntimeError("the transcript has tokens without utterances or speakers: run diarize first")
    speakers_from_turns(doc, speaker_map)
    by_label = {s.label: s.id for s in doc.speakers}
    label_of = {s.id: s.label for s in doc.speakers}
    rep = {"new": 0, "speakers_set": 0, "review": 0, "split_p": 0}

    out: list[Utterance] = []
    for u in doc.utterances:
        last = None
        for w in u.words:                       # speaker per word (untimed words: the one before)
            lab = _speaker_at(w, turns)
            w.speaker = by_label.get(lab, last) if lab else last
            last = w.speaker
        if u.src is not None:                   # an existing <u>: only a missing speaker is added
            if not u.speaker and u.words:
                u.speaker, _ = _majority(u.words)
                rep["speakers_set"] += 1 if u.speaker else 0
            for w in u.words:
                w.speaker = u.speaker
            out.append(u)
            continue
        if not u.words:
            continue
        if snap:
            snap_speaker_changes(u.words, max_shift=snap_shift)
        is_p = u.parent_tag == "p"
        pieces = _pieces(u.words, _cuts_p(u.words) if is_p else _cuts_free(u.words, split_gap))
        rep["split_p"] += max(0, len(pieces) - 1) if is_p else 0
        for ws in pieces:
            who, other = _majority(ws)
            timed = [w for w in ws if w.start is not None and w.end is not None]
            nu = Utterance(id=f"new-{len(out) + 1}", start=min((w.start for w in timed), default=None),
                           end=max((w.end for w in timed), default=None), speaker=who, words=ws,
                           parent=u.parent, parent_tag=u.parent_tag, new=True)
            for w in ws:
                w.speaker = who
            if is_p and other >= P_MINORITY:
                nu.review = "speaker"
                rep["review"] += 1
            mine = label_of.get(who)
            if nu.start is not None and nu.end is not None:
                nu.overlap = any(t.speaker != mine and _overlap(nu.start, nu.end, t.start, t.end) >= OVERLAP_MIN
                                 for t in doc.turns)
            out.append(nu)
            rep["new"] += 1
    doc.utterances = out
    return rep


def summary(doc: Doc, rep: dict) -> str:
    s = f"assign: {rep['new']} new utterance(s)"
    if rep["speakers_set"]:
        s += f", speakers for {rep['speakers_set']} existing one(s)"
    if rep["split_p"]:
        s += f", {rep['split_p']} split(s) inside a <p>"
    if rep["review"]:
        s += f", {rep['review']} marked review=\"speaker\""
    persons = (doc.run or {}).get("transcript_read", {}).get("persons") or []
    ids = [sp.id for sp in doc.speakers]
    if persons and not set(ids) <= set(persons):
        s += (f"; speakers {', '.join(ids)} are diarization labels: map them to the header's persons "
              f"({', '.join(persons)}) with --speaker-map, e.g. "
              + "{\"" + (doc.speakers[0].label if doc.speakers else "SPEAKER_00") + "\": {\"id\": \"" + persons[0] + "\"}}")
    return s
