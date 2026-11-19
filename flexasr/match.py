"""The match stage: an existing transcript takes its times from the ASR output of the same audio.

The transcript wins: its tokens stay as they are and only get times. The ASR words (``doc.hypothesis``)
are matched to them in two passes: whole words on a normalized form (case, accents, punctuation and
apostrophes left out), then, in the stretches between those matches, single characters, which bridges
tokenization differences ("qu'est-ce" as one ASR word and two tokens, or the reverse). A matched token
takes the time of the characters it matched; a spoken token that did not match gets an estimated time
from its neighbours (``estimate.py``, ``timing="estimated"``); punctuation, events and comments get none.

Times already in the transcript are limits, not a separate code path: a ``<u>`` with start and end is
matched only against the ASR words in that stretch (plus a margin), and untimed utterances between two
timed ones only against the stretch between them. With no times at all, the whole file is one block.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from .doc import Doc, Utterance, Word
from .estimate import spread
from .tokens import _EVENT

MARGIN = 1.0              # seconds of ASR output around an utterance's given times
MIN_SHARE = 0.5           # a token counts as matched when at least this share of its characters matched
SUSPECT_SHARE = 0.3       # an utterance with given times and less than this share matched: its times may be wrong
MAX_CHAR_CELLS = 4_000_000
MAX_SHIFT = 0.34          # in a stretch between matches: a token matches only ASR words at about the same relative place
MIN_LONE = 4              # a match of one word alone counts only for a word this long ("que" alone is anywhere)


def normalize(text: str) -> str:
    """Letters and digits only, lower case, without accents: what both sides are compared on."""
    t = unicodedata.normalize("NFD", unicodedata.normalize("NFKC", text).casefold())
    return "".join(c for c in t if unicodedata.category(c)[0] in "LN")


def spoken(w: Word) -> bool:
    if w.kind in ("punct", "event"):
        return False
    t = w.text.strip()
    return bool(normalize(t)) and not _EVENT.match(t)


@dataclass
class Block:
    utterances: list[Utterance]
    lo: Optional[float]                  # the stretch of audio this block's words lie in (None: open)
    hi: Optional[float]
    given: bool                          # lo/hi are the utterance's own times


@dataclass
class Report:
    tokens: int = 0
    not_spoken: int = 0
    given: int = 0
    matched: int = 0
    matched_partly: int = 0              # by characters (tokenization differs)
    estimated: int = 0
    untimed: int = 0                     # spoken, but nothing to estimate from
    hypothesis_words: int = 0
    hypothesis_unused: int = 0
    hypothesis_unused_seconds: float = 0.0
    suspect_utterances: list[str] = field(default_factory=list)

    def summary(self) -> str:
        sp = self.tokens - self.not_spoken
        s = (f"match: {sp} spoken token(s): {self.matched + self.matched_partly} matched to the ASR words"
             f" ({self.matched_partly} by characters), {self.estimated} estimated, {self.given} kept as given,"
             f" {self.untimed} left without times; {self.not_spoken} not spoken (punctuation, events)")
        if self.hypothesis_unused:
            s += (f"; {self.hypothesis_unused} ASR word(s), {self.hypothesis_unused_seconds:.1f} s, not in the transcript"
                  " (untranscribed speech, or misrecognized)")
        if self.suspect_utterances:
            s += (f"; given times may be wrong for {len(self.suspect_utterances)} utterance(s): "
                  + ", ".join(self.suspect_utterances[:10]) + (" …" if len(self.suspect_utterances) > 10 else ""))
        return s


def blocks(doc: Doc) -> list[Block]:
    out: list[Block] = []
    run: list[Utterance] = []
    prev_end: Optional[float] = None
    for u in doc.utterances:
        if u.start is not None and u.end is not None and u.end > u.start:
            if run:
                out.append(Block(run, prev_end, u.start, False))
                run = []
            out.append(Block([u], u.start, u.end, True))
            prev_end = u.end
        else:
            run.append(u)
    if run:
        out.append(Block(run, prev_end, doc.audio.duration, False))
    return out


def _time(h: Word, hn: str, k: int) -> float:
    return h.start + (h.end - h.start) * k / max(1, len(hn))


def _by_chars(toks: list[tuple[Word, str]], hyp: list[tuple[Word, str]], used: set[int], hyp_base: int,
              rep: Report) -> None:
    if not toks or not hyp:
        return
    tstr, tmap = [], []
    for i, (_, n) in enumerate(toks):
        tstr.extend(n)
        tmap.extend((i, k) for k in range(len(n)))
    hstr, hmap = [], []
    for j, (_, n) in enumerate(hyp):
        hstr.extend(n)
        hmap.extend((j, k) for k in range(len(n)))
    if len(tstr) * len(hstr) > MAX_CHAR_CELLS:
        return                               # too long a stretch to compare by characters: estimated instead
    hits: dict[int, list[tuple[int, int, int]]] = {}          # token -> [(offset in token, hyp index, offset in hyp)]
    for a, b, size in SequenceMatcher(None, tstr, hstr, autojunk=False).get_matching_blocks():
        if size == 0:
            continue
        if size == 1:                        # one character: only a one-letter word on both sides ("a", "y", "à")
            ti, _ = tmap[a]
            hj, _ = hmap[b]
            if len(toks[ti][1]) != 1 or len(hyp[hj][1]) != 1:
                continue
        for d in range(size):
            ti, tk = tmap[a + d]
            hj, hk = hmap[b + d]
            hits.setdefault(ti, []).append((tk, hj, hk))
    for ti, hs in hits.items():
        w, n = toks[ti]
        if len(hs) < MIN_SHARE * len(n):
            continue
        hs.sort()
        (_, j0, k0), (_, j1, k1) = hs[0], hs[-1]
        if len(toks) > 3 and abs((ti + 0.5) / len(toks) - (j0 + 0.5) / len(hyp)) > MAX_SHIFT:
            continue                         # a short word matched far from where it would be: chance
        s = _time(hyp[j0][0], hyp[j0][1], k0)
        e = _time(hyp[j1][0], hyp[j1][1], k1 + 1)
        if e <= s:
            continue
        w.start, w.end, w.timing = round(s, 3), round(e, 3), None
        used.update(hyp_base + j for j in range(j0, j1 + 1))
        rep.matched_partly += 1


def _match_block(toks: list[tuple[Word, str]], hyp: list[tuple[Word, str]], used: set[int], hyp_base: int,
                 rep: Report) -> None:
    a = [n for _, n in toks]
    b = [n for _, n in hyp]
    pa = pb = 0
    blocks = [m for m in SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks()
              if m.size > 1 or (m.size == 1 and len(a[m.a]) >= MIN_LONE)]
    blocks.append((len(a), len(b), 0))
    for i, j, size in blocks:
        if size == 0 and (i, j) != (len(a), len(b)):
            continue
        _by_chars(toks[pa:i], hyp[pb:j], used, hyp_base + pb, rep)
        for d in range(size):
            w, h = toks[i + d][0], hyp[j + d][0]
            w.start, w.end, w.timing = h.start, h.end, None
            if w.conf is None and h.conf is not None:
                w.conf = h.conf
            used.add(hyp_base + j + d)
            rep.matched += 1
        pa, pb = i + size, j + size


def _estimate(words: list[Word], lo: Optional[float], hi: Optional[float], rep: Report, speech=None) -> None:
    """Spoken words still without times get them from the timed words (or block edges) around them."""
    i, n = 0, len(words)
    while i < n:
        w = words[i]
        if not spoken(w) or w.start is not None:
            i += 1
            continue
        j = i
        while j < n and (words[j].start is None):     # the run: untimed words, punctuation among them
            j += 1
        run = words[i:j]
        while run and not spoken(run[-1]):
            run.pop()
        left = next((x.end for x in reversed(words[:i]) if x.end is not None), lo)
        right = next((x.start for x in words[j:] if x.start is not None), hi)
        flags = [spoken(x) for x in run]
        got = spread(run, flags, left, right, speech) if left is not None and right is not None else 0
        rep.estimated += got
        rep.untimed += sum(flags) - got
        i = j


def match(doc: Doc, margin: float = MARGIN, speech=None) -> Report:
    """``speech``: where someone speaks (``speech.py``); estimated times are spread over it, not over silence."""
    rep = Report()
    hyp = sorted((w for u in doc.hypothesis for w in u.words
                  if w.start is not None and w.end is not None and normalize(w.text)), key=lambda w: w.start)
    rep.hypothesis_words = len(hyp)
    words = list(doc.words())
    rep.tokens = len(words)
    rep.not_spoken = sum(1 for w in words if not spoken(w))
    rep.given = sum(1 for w in words if spoken(w) and w.timing == "given")
    todo = [w for w in words if spoken(w) and w.timing != "given"]
    if todo and not hyp:
        raise RuntimeError("the transcriber gave no word times to match; choose one that does (see `flexasr models "
                           "--task transcribe`) or give an aligner (--model align=…)")
    used: set[int] = set()
    for bl in blocks(doc):
        lo = -1e9 if bl.lo is None else bl.lo - (margin if bl.given else 0)
        hi = 1e9 if bl.hi is None else bl.hi + (margin if bl.given else 0)
        idx = [k for k, h in enumerate(hyp) if lo <= (h.start + h.end) / 2 <= hi]
        bwords = [w for u in bl.utterances for w in u.words]
        toks = [(w, normalize(w.text)) for w in bwords if spoken(w) and w.timing != "given"]
        if idx:
            base = idx[0]
            seg = [(hyp[k], normalize(hyp[k].text)) for k in range(idx[0], idx[-1] + 1)]
            before = rep.matched + rep.matched_partly
            _match_block(toks, seg, used, base, rep)
            got = rep.matched + rep.matched_partly - before
            if bl.given and len(toks) >= 4 and got < SUSPECT_SHARE * len(toks):
                rep.suspect_utterances.append(bl.utterances[0].id)
        elif bl.given and len(toks) >= 4:
            rep.suspect_utterances.append(bl.utterances[0].id)
        _estimate(bwords, bl.lo, bl.hi, rep, speech)
    unused = [h for k, h in enumerate(hyp) if k not in used]
    rep.hypothesis_unused = len(unused)
    rep.hypothesis_unused_seconds = round(sum(h.end - h.start for h in unused), 3)
    for u in doc.utterances:
        timed = [w for w in u.words if w.start is not None and w.end is not None]
        if timed and (u.start is None or u.end is None):
            u.start, u.end = min(w.start for w in timed), max(w.end for w in timed)
    return rep
