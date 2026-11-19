"""An existing TEITOK transcript as a Doc, so a run can add times to it.

The transcript wins: its tokens, utterances and speakers become the Doc as they are, and every word and
utterance remembers the element it came from (``src``: its index among the file's start tags, in
document order, as ``xmlpatch.scan`` numbers them). Write-back (``writers/timeback.py``) puts the times
on exactly those elements and changes nothing else.

Read here: ``<tok>`` (its text, or ``@form`` when it has none) and ``<vocal><desc>`` (fillers, as
flexasr writes them), inside ``<u>`` or not; ``<u @id @who @start @end>``; the language from
``langUsage/language/@ident``; the media from ``recording/media/@url``. Times already on an element
are kept (``timing="given"``). A ``<u>`` with text but no tokens is kept as it is (counted in the report).
"""

from __future__ import annotations

import hashlib
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .. import langs, xmlpatch
from ..doc import Audio, Doc, Transcript, Utterance, Word
from ..tokens import _is_punct

# Elements a new <u> stays inside: a transcriber's <p> is an utterance boundary, the others are structure.
CONTAINERS = {"p", "ab", "div", "body", "text", "sp", "lg", "l", "front", "back"}


def _local(tag) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def _num(v: Optional[str]) -> Optional[float]:
    try:
        return float(v) if v not in (None, "") else None
    except ValueError:
        return None


def _text(el: ET.Element) -> str:
    t = "".join(el.itertext()).strip()
    return t or (el.get("form") or "").strip()


def elements(text: str) -> tuple[list[ET.Element], list[xmlpatch.Tag]]:
    """The parsed elements and their start tags in the file, index for index (checked)."""
    root = ET.fromstring(text)
    els = list(root.iter())
    tags = xmlpatch.scan(text)
    if len(els) != len(tags):
        raise xmlpatch.PatchError(f"the parser sees {len(els)} elements, the scanner {len(tags)} (entities?)")
    for el, tg in zip(els, tags):
        if _local(el.tag) != tg.name.rsplit(":", 1)[-1]:
            raise xmlpatch.PatchError(f"element order differs between parser and scanner at <{tg.name}>, line {tg.line}")
    return els, tags


def decode(raw: bytes, path: str | Path) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError(f"{path}: has a byte-order mark; only plain UTF-8 files are edited")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise ValueError(f"{path}: not UTF-8 ({e}); only UTF-8 files are edited") from None


def find_media(xml_path: Path, url: Optional[str]) -> Optional[Path]:
    """The media file named in the header: relative to the file, or to a folder above it (a TEITOK
    project keeps xmlfiles/ and Audio/ side by side), or in that Audio/ folder."""
    if not url or "://" in url:
        return None
    rel = Path(url)
    if rel.is_absolute():
        return rel if rel.exists() else None
    for base in [xml_path.parent, *list(xml_path.parent.parents)[:3]]:
        for cand in (base / rel, base / "Audio" / rel):       # TEITOK also reads a bare file name from Audio/
            if cand.exists():
                return cand
    return None


def read(path: str | Path, audio: Optional[str | Path] = None) -> Doc:
    path = Path(path)
    raw = path.read_bytes()
    text = decode(raw, path)
    els, _ = elements(text)
    parent = {c: p for p in els for c in p}
    index = {id(el): i for i, el in enumerate(els)}

    lang = media = None
    for el in els:
        n = _local(el.tag)
        if n == "language" and lang is None and el.get("ident") and _local(parent.get(el, el).tag) == "langUsage":
            lang = el.get("ident")
        elif n == "media" and media is None and el.get("url"):
            media = el.get("url")

    if audio is None:
        found = find_media(path, media)
        if found is None:
            raise ValueError(f"{path}: the media file ({media or 'none named in the header'}) is not found; give --audio")
        audio = found
    doc = Doc(audio=Audio(path=str(audio)), language=langs.norm(lang) if lang else None,
              transcript=Transcript(path=str(path), sha256=hashlib.sha256(raw).hexdigest()))

    scope = next((el for el in els if _local(el.tag) == "text"), els[0])
    loose: Optional[Utterance] = None             # tokens outside any <u>, in runs per container
    by_src: dict[int, Utterance] = {}
    untokenized: list[tuple[str, Optional[str]]] = []
    persons = [el.get("id") for el in els if _local(el.tag) == "person" and el.get("id")]
    for el in scope.iter():
        n = _local(el.tag)
        if n == "u":
            loose = None
            u = Utterance(id=el.get("id") or f"u@{index[id(el)]}", start=_num(el.get("start")),
                          end=_num(el.get("end")), speaker=el.get("who"), src=index[id(el)])
            doc.utterances.append(u)
            by_src[u.src] = u
            if not any(_local(d.tag) in ("tok", "vocal") for d in el.iter()) and "".join(el.itertext()).strip():
                untokenized.append((u.id, u.speaker))
            continue
        if n not in ("tok", "vocal"):
            continue
        if n == "vocal":
            desc = next((d for d in el if _local(d.tag) == "desc"), None)
            if desc is None or not "".join(desc.itertext()).strip():
                continue
            w = Word(text="".join(desc.itertext()).strip(), kind="filler")
        else:
            if any(_local(a.tag) == "tok" for a in _ancestors(el, parent)):
                continue                           # a tok inside a tok: the outer one is the word
            t = _text(el)
            w = Word(text=t, kind="punct" if t and all(_is_punct(c) for c in t) else "word")
        w.src = index[id(el)]
        s, e = _num(el.get("start")), _num(el.get("end"))
        if s is not None and e is not None:
            w.start, w.end, w.timing = s, e, "given"
        u_el = next((a for a in _ancestors(el, parent) if _local(a.tag) == "u"), None)
        if u_el is not None:
            u = by_src[index[id(u_el)]]
        else:
            box = next((a for a in _ancestors(el, parent) if _local(a.tag) in CONTAINERS), scope)
            if loose is None or loose.parent != index[id(box)]:
                loose = Utterance(id=f"block-{len(doc.utterances) + 1}", start=None, end=None,
                                  parent=index[id(box)], parent_tag=_local(box.tag))
                doc.utterances.append(loose)
            u = loose
        w.speaker = u.speaker
        u.words.append(w)
    doc.run["transcript_read"] = {"utterances": sum(1 for u in doc.utterances if u.src is not None),
                                  "untokenized": [list(x) for x in untokenized],
                                  "tokens": sum(1 for _ in doc.words()), "persons": persons}
    if not any(True for _ in doc.words()):
        raise ValueError(f"{path}: the transcript has no tokens; tokenize it first (for instance with xmltokenize, or "
                         "in TEITOK), then run again")
    return doc


def untokenized_note(doc: Doc) -> Optional[str]:
    """What to say about utterances with text but no tokens: a speaker left untokenized throughout is deliberate
    (an interviewer, say); single utterances added as plain text need tokenizing to get times."""
    info = (doc.run or {}).get("transcript_read", {})
    plain = [tuple(x) for x in info.get("untokenized", [])]
    if not plain:
        return None
    tokenized_speakers = {u.speaker for u in doc.utterances if u.src is not None and u.words}
    whole = sorted({sp for _, sp in plain if sp and sp not in tokenized_speakers})
    rest = [uid for uid, sp in plain if not sp or sp in tokenized_speakers]
    out = []
    if whole:
        out.append(f"{', '.join(whole)} speak only in untokenized utterances (left as they are, as intended)")
    if rest:
        out.append(f"{len(rest)} utterance(s) have plain text but no tokens ({', '.join(rest[:8])}"
                   + (" …" if len(rest) > 8 else "") + "): tokenize them (in TEITOK, or with xmltokenize) and run again "
                   "to time them")
    return "; ".join(out)


def _ancestors(el: ET.Element, parent: dict):
    while el in parent:
        el = parent[el]
        yield el
