"""Speakers for words, utterances per speaker turn, overlap marks (dev/RESHAPE-2026-10.md §3.3).

Words get the speaker of the *exclusive* diarization turn they overlap most (one speaker at a time);
the *full* turns (which may overlap) mark utterances that overlap someone else's speech, for review.
A speaker map renames diarization labels and sets names and roles; roles listed as untokenized keep
their text but get no ``<tok>``s in the output.
"""

from __future__ import annotations

from typing import Optional

from .doc import Doc, Speaker, Turn, Utterance, Word


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _speaker_at(w: Word, turns: list[Turn]) -> Optional[str]:
    if w.start is None or w.end is None or not turns:
        return None
    best, best_ov = None, 0.0
    for t in turns:
        ov = _overlap(w.start, max(w.end, w.start + 1e-3), t.start, t.end)
        if ov > best_ov:
            best, best_ov = t.speaker, ov
    if best is not None:
        return best
    mid = (w.start + w.end) / 2      # in a gap between turns: the nearest turn
    return min(turns, key=lambda t: min(abs(mid - t.start), abs(mid - t.end))).speaker


def speakers_from_turns(doc: Doc, speaker_map: Optional[dict] = None,
                        untokenized_roles: tuple[str, ...] = ()) -> None:
    """``doc.speakers`` in order of first appearance; ``speaker_map``: label → {id, name, role}."""
    speaker_map = speaker_map or {}
    seen: list[str] = []
    for t in sorted(doc.turns_exclusive or doc.turns, key=lambda t: t.start):
        if t.speaker not in seen:
            seen.append(t.speaker)
    out = []
    for i, label in enumerate(seen, 1):
        m = speaker_map.get(label, {})
        role = m.get("role")
        out.append(Speaker(id=m.get("id", f"spk{i}"), label=label, name=m.get("name"), role=role,
                           tokenize=role not in untokenized_roles))
    doc.speakers = out


def assign(doc: Doc, speaker_map: Optional[dict] = None, untokenized_roles: tuple[str, ...] = (),
           split_gap: float = 2.0, overlap_min: float = 0.2) -> None:
    """Rebuild ``doc.utterances``: one per stretch of one speaker (split at gaps > ``split_gap`` s)."""
    speakers_from_turns(doc, speaker_map, untokenized_roles)
    by_label = {s.label: s.id for s in doc.speakers}
    excl = doc.turns_exclusive or doc.turns
    words = [w for w in doc.words()]
    last = None
    for w in words:
        lab = _speaker_at(w, excl)
        w.speaker = by_label.get(lab, last) if lab else last
        last = w.speaker
    utts: list[Utterance] = []
    cur: Optional[Utterance] = None
    for w in words:
        gap = (w.start - cur.end) if (cur and w.start is not None and cur.end is not None) else 0.0
        if cur is None or w.speaker != cur.speaker or gap > split_gap:
            cur = Utterance(id=f"u-{len(utts) + 1}", start=w.start, end=w.end, speaker=w.speaker)
            utts.append(cur)
        cur.words.append(w)
        if w.end is not None:
            cur.end = w.end if cur.end is None else max(cur.end, w.end)
        if cur.start is None:
            cur.start = w.start
    label_of = {s.id: s.label for s in doc.speakers}
    for u in utts:
        if u.start is None or u.end is None:
            continue
        mine = label_of.get(u.speaker)
        u.overlap = any(t.speaker != mine and _overlap(u.start, u.end, t.start, t.end) >= overlap_min
                        for t in doc.turns)
    doc.utterances = utts
