"""TEITOK XML from a Doc: timed ``<u>`` and ``<tok>``, speakers and roles, verbatim elements.

Follows the encoding of the existing TEITOK spoken corpora (dev/RESHAPE-2026-10.md §3.3b):
``teiHeader/recordingStmt/recording/media@url`` (relative ``Audio/…``), ``<u who start end>`` with a
plain speaker code, persons in ``particDesc/listPerson``, plain ``id`` attributes, and
``<vocal><desc>``, ``<pause type>``, ``<del reason>``/``<tok form="--">``, ``<incident>``.
A per-project table can switch elements off or rename them (``Encoding``).

Provenance (§3.5b): every layer's provider, model, source, revision, licence and restrictions go into
``encodingDesc/appInfo``, so restrictions travel with the corpus.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .. import __version__
from ..doc import Doc, Word


@dataclass
class Encoding:
    """Per-project choices; the defaults are what the TEITOK spoken corpora use."""

    media_dir: str = "Audio"
    pause_long: float = 1.0                   # ≥ this: type="long", else "short"
    pauses: bool = True
    vocal: bool = True                        # fillers as <vocal>; False: plain <tok>
    deletions: dict[str, str] = field(default_factory=lambda: {
        "truncated": "truncated", "repetition": "repetition", "reformulation": "reformulation"})
    events: str = "incident"                  # element for [laughter] etc.; "" = drop
    overlap_attr: bool = True                 # mark overlapping <u> for review


def _t(x: Optional[float]) -> Optional[str]:
    return None if x is None else f"{x:.3f}"


def _set(el: ET.Element, **attrs):
    for k, v in attrs.items():
        if v is not None:
            el.set(k, str(v))
    return el


def build(doc: Doc, enc: Optional[Encoding] = None, text_id: Optional[str] = None) -> ET.Element:
    enc = enc or Encoding()
    stem = Path(doc.audio.path).stem
    tei = ET.Element("TEI")
    hdr = ET.SubElement(tei, "teiHeader")
    fd = ET.SubElement(hdr, "fileDesc")
    ET.SubElement(ET.SubElement(fd, "titleStmt"), "title").text = stem
    ET.SubElement(ET.SubElement(fd, "publicationStmt"), "p").text = "Transcribed with flexasr"
    if doc.speakers or doc.language:
        pd = ET.SubElement(hdr, "profileDesc")
        if doc.language:
            _set(ET.SubElement(ET.SubElement(pd, "langUsage"), "language"), ident=doc.language)
        if doc.speakers:
            lp = ET.SubElement(ET.SubElement(pd, "particDesc"), "listPerson")
            for s in doc.speakers:
                p = _set(ET.SubElement(lp, "person"), id=s.id, role=s.role, n=s.label)
                if s.name:
                    ET.SubElement(p, "persName").text = s.name
    ai = ET.SubElement(ET.SubElement(hdr, "encodingDesc"), "appInfo")
    _set(ET.SubElement(ai, "application"), ident="flexasr", version=__version__, type="pipeline")
    for p in doc.provenance:
        app = _set(ET.SubElement(ai, "application"), ident=p.provider, version=p.version, type=p.stage)
        if p.model:
            ET.SubElement(app, "label").text = p.model
        if p.source:
            _set(ET.SubElement(app, "ptr"), target=p.source + (f"@{p.revision}" if p.revision else ""))
        bits = [f"licence: {p.licence}"] if p.licence else []
        if p.restricted:
            bits.append("restricted: " + ", ".join(p.restricted))
        if bits:
            ET.SubElement(app, "desc").text = "; ".join(bits)
    rec = ET.SubElement(ET.SubElement(hdr, "recordingStmt"), "recording")
    url = f"{enc.media_dir}/{Path(doc.audio.path).name}" if enc.media_dir else Path(doc.audio.path).name
    _set(ET.SubElement(rec, "media"), url=url, mimeType=_mime(doc.audio.path))

    text = _set(ET.SubElement(tei, "text"), id=text_id or stem)
    body = ET.SubElement(text, "body")
    tokenize = {s.id: s.tokenize for s in doc.speakers}
    pauses = {}                           # by end time: written before the next timed word
    for p in doc.pauses:
        pauses.setdefault(round(p.end, 3), []).append(p)
    wn = 0
    for u in doc.utterances:
        ue = _set(ET.SubElement(body, "u"), id=u.id, who=u.speaker, start=_t(u.start), end=_t(u.end))
        if u.overlap and enc.overlap_attr:
            ue.set("overlap", "review")
        if not tokenize.get(u.speaker, True):
            ue.text = " ".join(w.text for w in u.words)
            continue
        for w in u.words:
            if enc.pauses and w.start is not None:
                for p in pauses.get(round(w.start, 3), []):
                    if p.speaker == u.speaker:
                        dur = p.end - p.start
                        pe = _set(ET.SubElement(ue, "pause"), type="long" if dur >= enc.pause_long else "short",
                                  dur=f"{dur:.3f}", start=_t(p.start), end=_t(p.end))
                        pe.tail = " "
            el = _word(ue, w, enc, wn + 1)
            if el is not None:
                el.tail = " " if w.space_after else ""     # the text between tokens, as spoken/written
                if el.tag in ("tok", "del"):
                    wn += 1
    _indent(tei)
    return tei


def _word(ue: ET.Element, w: Word, enc: Encoding, n: int) -> Optional[ET.Element]:
    if w.kind == "filler" and enc.vocal:
        v = _set(ET.SubElement(ue, "vocal"), start=_t(w.start), end=_t(w.end))
        ET.SubElement(v, "desc").text = w.text
        return v
    if w.kind == "event":
        if not enc.events:
            return None
        ev = _set(ET.SubElement(ue, enc.events), start=_t(w.start), end=_t(w.end))
        ET.SubElement(ev, "desc").text = w.text
        return ev
    parent = ue
    if w.kind in enc.deletions:
        parent = _set(ET.SubElement(ue, "del"), reason=enc.deletions[w.kind])
    tok = _set(ET.SubElement(parent, "tok"), id=f"w-{n}", start=_t(w.start), end=_t(w.end))
    if parent is not ue:
        tok.set("form", "--")                     # drops out of the normalized text, as in TEITOK corpora
    if w.orig and w.orig != w.text:
        tok.set("orig", w.orig)
    tok.text = w.text
    return parent if parent is not ue else tok


def _mime(path: str) -> str:
    ext = Path(path).suffix.lower()
    return {".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".flac": "audio/flac",
            ".ogg": "audio/ogg", ".mp4": "video/mp4", ".webm": "video/webm"}.get(ext, "audio/" + ext.lstrip("."))


def _indent(el: ET.Element, level: int = 0) -> None:
    """Line breaks between elements (inside <u>, tokens stay on one line, space-separated)."""
    pad = "\n" + "  " * level
    if el.tag == "u":                       # tails inside <u> were set by build(): keep them
        if len(el):
            el[-1].tail = pad
            if el.text is None:
                el.text = ""
        return
    if len(el):
        if not el.text or not el.text.strip():
            el.text = pad + "  "
        for c in el:
            _indent(c, level + 1)
            c.tail = pad + "  "
        el[-1].tail = pad


def write(doc: Doc, path: str | Path, enc: Optional[Encoding] = None) -> None:
    tree = ET.ElementTree(build(doc, enc))
    tree.write(str(path), encoding="utf-8", xml_declaration=True)
