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
import json
from pathlib import Path
from typing import Optional

from .. import __version__
from ..doc import Doc, Word


@dataclass
class Encoding:
    """Per-project choices; the defaults are what the TEITOK spoken corpora use."""

    media_dir: str = "Audio"
    media_url: Optional[str] = None           # explicit media url (e.g. "Audio/sub/x.wav"); else media_dir/name
    conf: bool = True                         # word confidence (when the model gives one) as @conf on <tok>
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
    pub = ET.SubElement(fd, "publicationStmt")
    ET.SubElement(pub, "p").text = "Transcribed with flexasr"
    _licence_notes(pub, doc)
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
    enc_desc = ET.SubElement(hdr, "encodingDesc")
    _editorial(enc_desc, doc)
    ai = ET.SubElement(enc_desc, "appInfo")
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
        st = p.settings or {}
        if st.get("device"):
            bits.append(f"device: {st['device']}")
        if st.get("options"):
            bits.append("options: " + json.dumps(st["options"], ensure_ascii=False, sort_keys=True))
        if bits:
            ET.SubElement(app, "desc").text = "; ".join(bits)
    rec = ET.SubElement(ET.SubElement(hdr, "recordingStmt"), "recording")
    url = enc.media_url or (f"{enc.media_dir}/{Path(doc.audio.path).name}" if enc.media_dir
                            else Path(doc.audio.path).name)
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


def _editorial(enc_desc: ET.Element, doc: Doc) -> None:
    """How the transcription was made, in words: always written, whatever the licences are."""
    r = doc.run or {}
    ed = ET.SubElement(enc_desc, "editorialDecl")
    lines = [f"Automatic transcription ({doc.mode} mode) of {Path(doc.audio.path).name}"
             + (f", language {doc.language}" if doc.language else "")
             + (f", {doc.audio.duration:.1f} s" if doc.audio.duration else "")
             + (f", run on {r['date']}" if r.get("date") else "") + "."]
    steps = [f"{p.stage}: {p.model or p.provider} ({p.provider}" + (f" {p.version}" if p.version else "") + ")"
             for p in doc.provenance]
    if steps:
        lines.append("Stages and models: " + "; ".join(steps) + ".")
    if r.get("speakers_requested"):
        lines.append("Speakers requested: " + ", ".join(f"{k}={v}" for k, v in r["speakers_requested"].items()) + ".")
    if doc.speakers:
        lines.append(f"Speakers found: {len(doc.speakers)}.")
    if r.get("untokenized_roles"):
        lines.append("Roles transcribed without tokens: " + ", ".join(r["untokenized_roles"]) + ".")
    if r:
        lines.append(f"Utterances split at pauses of {r.get('split_gap')} s; pauses from {r.get('pause_min')} s "
                     f"are marked; restricted models allowed: {'yes' if r.get('allow_restricted') else 'no'}.")
    if r.get("overrides") and any(r["overrides"].values()):
        lines.append("Router overridden: " + json.dumps(r["overrides"], ensure_ascii=False, sort_keys=True) + ".")
    lines.append("The transcription is machine output and has not been corrected.")
    for ln in lines:
        ET.SubElement(ed, "p").text = ln


def _licence_notes(pub: ET.Element, doc: Doc) -> None:
    """Models whose licence differs from flexasr's own (MIT) are named in the header, and a restriction
    on what they produce (e.g. non-commercial) is stated as a restriction on the file itself."""
    notes = []
    for p in doc.provenance:
        if not p.licence or p.licence.lower() in ("n/a", "mit") or p.licence.startswith("MIT "):
            continue
        what = f"{p.stage} model {p.model or p.provider}"
        if p.restricted:
            notes.append(f"Restricted ({', '.join(p.restricted)}): this transcription was produced with the "
                         f"{what}, licence {p.licence}; its licence limits how the output may be used.")
        else:
            notes.append(f"The {what} is used under licence {p.licence}.")
    if notes:
        av = ET.SubElement(pub, "availability")
        if any(p.restricted for p in doc.provenance):
            av.set("status", "restricted")
        for n in notes:
            ET.SubElement(av, "licence").text = n


def _orig(w: Word) -> Optional[str]:
    """The model's own spelling, when the encoding changed it (kept as an attribute)."""
    return w.orig if w.orig and w.orig != w.text else None


def _word(ue: ET.Element, w: Word, enc: Encoding, n: int) -> Optional[ET.Element]:
    if w.kind == "filler" and enc.vocal:
        v = _set(ET.SubElement(ue, "vocal"), start=_t(w.start), end=_t(w.end), orig=_orig(w))
        ET.SubElement(v, "desc").text = w.text
        return v
    if w.kind == "event":
        if not enc.events:
            return None
        ev = _set(ET.SubElement(ue, enc.events), start=_t(w.start), end=_t(w.end), orig=_orig(w))
        ET.SubElement(ev, "desc").text = w.text
        return ev
    parent = ue
    if w.kind in enc.deletions:
        parent = _set(ET.SubElement(ue, "del"), reason=enc.deletions[w.kind])
    tok = _set(ET.SubElement(parent, "tok"), id=f"w-{n}", start=_t(w.start), end=_t(w.end))
    if parent is not ue:
        tok.set("form", "--")                     # drops out of the normalized text, as in TEITOK corpora
    if _orig(w):
        tok.set("orig", w.orig)
    if enc.conf and w.conf is not None:
        tok.set("conf", f"{w.conf:.3f}")
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
