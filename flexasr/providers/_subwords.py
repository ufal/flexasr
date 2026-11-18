"""Words from the subword tokens of a transducer model (Parakeet, Canary through onnx-asr).

The model gives its tokens (SentencePiece pieces: a piece that starts a word has a leading space, punctuation and the
rest of a word come without one), the time each token starts, and the log-probability of each token. There is no end
time: the end of a word is where its last token with a letter in it starts plus one frame, or where the next word starts when that is
sooner. Word times are accurate to a frame (80 ms for these models).
"""

from __future__ import annotations

import math
from typing import Optional, Sequence

from ..doc import Word

FRAME = 0.08         # seconds per frame of the FastConformer encoder these models use


def words_from_tokens(tokens: Sequence[str], times: Optional[Sequence[float]], logprobs: Optional[Sequence[float]] = None,
                      offset: float = 0.0, limit: Optional[float] = None, frame: float = FRAME) -> list[Word]:
    """Join tokens into words. ``times``: when the model gives none (Canary through onnx-asr), the words get no times
    (the align stage supplies them). ``offset``: seconds to add to the token times (the start of the chunk they belong
    to); ``limit``: where the chunk ends (a word never ends later). ``conf`` of a word: the mean probability of its
    tokens (length-fair across the pieces of a word, as CrisperWhisper's word probability is)."""
    groups: list[list[int]] = []
    new_word = True
    for i, tok in enumerate(tokens):
        if not tok.strip() or tok.strip() == "▁":
            new_word = True              # a token that is only a space ends the word before it ("už", " ", "2", "0")
            continue
        if new_word or not groups or tok.startswith((" ", "▁")):
            groups.append([i])
        else:
            groups[-1].append(i)
        new_word = False
    words: list[Word] = []
    for g in groups:
        text = "".join(tokens[i] for i in g).replace("▁", " ").strip()
        if not text:
            continue
        conf = None
        if logprobs is not None:
            conf = round(sum(math.exp(min(0.0, float(logprobs[i]))) for i in g) / len(g), 3)
        if times is None:
            words.append(Word(text=text, conf=conf))
            continue
        # the end comes from the last token with a letter or digit in it: the model emits punctuation late (after a
        # pause, sometimes a second later), which would stretch the word over the silence
        last = next((i for i in reversed(g) if any(c.isalnum() for c in tokens[i])), g[-1])
        start = offset + float(times[g[0]])
        end = offset + float(times[last]) + frame
        words.append(Word(text=text, start=round(start, 3), end=round(end, 3), conf=conf))
    for k, w in enumerate(words):
        if w.start is None:
            continue
        nxt = words[k + 1].start if k + 1 < len(words) else None
        if nxt is not None and w.end > nxt:
            w.end = nxt
        if limit is not None and w.end > limit:
            w.end = round(max(w.start, limit), 3)
    return words
