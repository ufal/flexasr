"""Times written back into the transcript they were made for, changing nothing else.

Each word and utterance of a transcript Doc knows the element it came from (``src``); this sets
``start``/``end`` on those elements (``timing="estimated"`` for times from the text, ``conf`` where the
ASR gave one) and records how the times were made in ``encodingDesc/appInfo``. Everything else stays
byte for byte as it was (``xmlpatch.apply`` checks it); the result must parse again.

Never overwritten: times already on an element (they were given), and a file that changed after it
was read (its checksum is compared).
"""

from __future__ import annotations

import hashlib
import os
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from .. import __version__, xmlpatch
from ..doc import Doc, Provenance
from ..readers.teitok import _local, decode, elements


def _t(x: float) -> str:
    return f"{x:.3f}"


def _names(tag: xmlpatch.Tag) -> set[str]:
    return {a.name for a in tag.attrs}


def _application(doc: Doc, rep: dict) -> str:
    rec: Optional[Provenance] = next((p for p in reversed(doc.provenance) if p.stage == "transcribe"), None)
    al: Optional[Provenance] = next((p for p in reversed(doc.provenance) if p.stage == "align"), None)
    m = (doc.run or {}).get("match", {})
    date = (doc.run or {}).get("date")
    bits = [f"word times added{f' on {date}' if date else ''} from {Path(doc.audio.path).name}: "
            f"{m.get('matched', 0) + m.get('matched_partly', 0)} token(s) matched to the ASR words, "
            f"{m.get('estimated', 0)} estimated from the text (timing=\"estimated\"), "
            f"{rep['kept']} kept as they were"]
    if al:
        bits.append(f"aligned with {al.model or al.provider}")
    if rec and rec.licence:
        bits.append(f"licence: {rec.licence}")
    if rec and rec.restricted:
        bits.append("restricted: " + ", ".join(rec.restricted))
    x = xmlpatch.escape_attr
    out = f'<application ident="flexasr" version="{x(__version__)}" type="timing">'
    if rec and rec.model:
        out += f"<label>{xmlpatch.escape_text(rec.model)}</label>"
    if rec and rec.source:
        out += f'<ptr target="{x(rec.source + (f"@{rec.revision}" if rec.revision else ""))}"/>'
    return out + f"<desc>{xmlpatch.escape_text('; '.join(bits))}</desc></application>"


def _header_edit(text: str, els: list, tags: list, app: str):
    pos = {_local(el.tag): i for i, el in reversed(list(enumerate(els)))
           if _local(el.tag) in ("teiHeader", "encodingDesc", "appInfo")}
    if "appInfo" in pos:
        return xmlpatch.insert_edit(text, tags[pos["appInfo"]], app)
    if "encodingDesc" in pos:
        return xmlpatch.insert_edit(text, tags[pos["encodingDesc"]], f"<appInfo>{app}</appInfo>")
    if "teiHeader" in pos:
        return xmlpatch.insert_edit(text, tags[pos["teiHeader"]], f"<encodingDesc><appInfo>{app}</appInfo></encodingDesc>")
    return None


def _element_end(text: str, tag: xmlpatch.Tag) -> int:
    if tag.self_closing or tag.close_start is None:
        return tag.end
    return text.index(">", tag.close_start) + 1


def _new_utterances(doc: Doc, text: str, els: list, tags: list, rep: dict) -> list:
    """A start and an end tag around the tokens of each new utterance. The tags go around whole children of the
    element the tokens are in (a token inside inline markup takes that markup along), so the result nests."""
    new = [u for u in doc.utterances if u.new and u.words and u.parent is not None]
    if not new:
        return []
    index = {id(el): i for i, el in enumerate(els)}
    up = {index[id(c)]: index[id(p)] for p in els for c in p}
    used = {el.get("id") for el in els if el.get("id")}
    n, out = 0, []

    def unit(i: int, parent: int) -> int:
        while up.get(i) is not None and up[i] != parent:
            i = up[i]
        if up.get(i) != parent:
            raise xmlpatch.PatchError(f"element {i} is not inside element {parent}")
        return i

    for u in new:
        srcs = [w.src for w in u.words if w.src is not None]
        if not srcs:
            continue
        first, last = unit(srcs[0], u.parent), unit(srcs[-1], u.parent)
        n += 1
        while f"u-{n}" in used:
            n += 1
        attrs = {"id": f"u-{n}", "who": u.speaker, "start": None if u.start is None else _t(u.start),
                 "end": None if u.end is None else _t(u.end), "overlap": "review" if u.overlap else None,
                 "review": u.review}
        x = xmlpatch.escape_attr
        open_tag = "<u" + "".join(f' {k}="{x(v)}"' for k, v in attrs.items() if v) + ">"
        out.append((tags[first].start, tags[first].start, open_tag))
        end = _element_end(text, tags[last])
        out.append((end, end, "</u>"))
        rep["new_utterances"] += 1
    return out


def build(doc: Doc) -> tuple[bytes, dict]:
    """The transcript with the Doc's times, and what was done (counts)."""
    if not doc.transcript:
        raise ValueError("this document has no transcript to write back into")
    src = Path(doc.transcript.path)
    raw = src.read_bytes()
    if hashlib.sha256(raw).hexdigest() != doc.transcript.sha256:
        raise RuntimeError(f"{src} changed since it was read; run again on the current file")
    text = decode(raw, src)
    els, tags = elements(text)
    edits, rep = [], {"tokens": 0, "estimated": 0, "utterances": 0, "kept": 0, "new_utterances": 0, "header": False}
    for u in doc.utterances:
        if u.src is None:
            continue
        tag = tags[u.src]
        if tag.name.rsplit(":", 1)[-1] != "u":
            raise xmlpatch.PatchError(f"element {u.src} is <{tag.name}>, not the <u> that was read")
        names, vals = _names(tag), {}
        if u.start is not None and u.end is not None and not {"start", "end"} & names:
            vals.update(start=_t(u.start), end=_t(u.end))
        if u.speaker and "who" not in names:
            vals["who"] = u.speaker
        if vals:
            edits.append(xmlpatch.attrs_edit(text, tag, vals))
            rep["utterances"] += 1
    edits += _new_utterances(doc, text, els, tags, rep)
    for w in doc.words():
        if w.src is None or w.start is None or w.end is None:
            continue
        tag = tags[w.src]
        if tag.name.rsplit(":", 1)[-1] not in ("tok", "vocal"):
            raise xmlpatch.PatchError(f"element {w.src} is <{tag.name}>, not the token that was read")
        names = _names(tag)
        if w.timing == "given" or {"start", "end"} & names:
            rep["kept"] += 1
            continue
        vals = {"start": _t(w.start), "end": _t(w.end)}
        if w.timing == "estimated":
            vals["timing"] = "estimated"
            rep["estimated"] += 1
        if w.conf is not None and "conf" not in names and w.timing != "estimated":
            vals["conf"] = f"{w.conf:.3f}"
        edits.append(xmlpatch.attrs_edit(text, tag, vals))
        rep["tokens"] += 1
    head = _header_edit(text, els, tags, _application(doc, rep)) if edits else None
    if head:
        edits.append(head)
        rep["header"] = True
    new = xmlpatch.apply(text, edits)
    try:
        ET.fromstring(new)
    except ET.ParseError as e:                     # never expected: the edits are attribute values and one element
        raise xmlpatch.PatchError(f"the result does not parse: {e}") from None
    return new.encode("utf-8"), rep


def write(doc: Doc, path: str | Path) -> dict:
    data, rep = build(doc)
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return rep


def summary(rep: dict) -> str:
    return (f"write-back: times on {rep['tokens']} token(s) ({rep['estimated']} estimated), {rep['utterances']} "
            f"utterance(s) completed, {rep['new_utterances']} new utterance(s); {rep['kept']} token(s) kept their times"
            + ("; recorded in encodingDesc/appInfo" if rep["header"] else "; no teiHeader: not recorded in the file"))
