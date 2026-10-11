"""Language codes: flexasr uses ISO 639-3 internally; engines often want ISO 639-1.

Codes and names come from ``resources/languages.json`` in the shared models repository (the same
table flexipipe uses), so "nl", "nld", "dut", "Dutch" and "Nederlands" all resolve to ``nld``. When
it cannot be reached (nor is cached), a small built-in table of ISO 639-1 codes is used.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

# ISO 639-3 → 639-1 for the languages engines commonly name by two letters (offline fallback).
_TO_1 = {
    "afr": "af", "amh": "am", "ara": "ar", "aze": "az", "bel": "be", "ben": "bn", "bos": "bs", "bre": "br",
    "bul": "bg", "cat": "ca", "ces": "cs", "cym": "cy", "dan": "da", "deu": "de", "ell": "el", "eng": "en",
    "est": "et", "eus": "eu", "fao": "fo", "fas": "fa", "fin": "fi", "fra": "fr", "gle": "ga", "glg": "gl",
    "guj": "gu", "hau": "ha", "heb": "he", "hin": "hi", "hrv": "hr", "hun": "hu", "hye": "hy", "ind": "id",
    "isl": "is", "ita": "it", "jav": "jv", "jpn": "ja", "kat": "ka", "kaz": "kk", "khm": "km", "kor": "ko",
    "lat": "la", "lav": "lv", "lit": "lt", "ltz": "lb", "mal": "ml", "mar": "mr", "mkd": "mk", "mlt": "mt",
    "mon": "mn", "msa": "ms", "mya": "my", "nep": "ne", "nld": "nl", "nno": "nn", "nob": "nb", "nor": "no",
    "oci": "oc", "pan": "pa", "pol": "pl", "por": "pt", "pus": "ps", "ron": "ro", "rus": "ru", "san": "sa",
    "sin": "si", "slk": "sk", "slv": "sl", "sna": "sn", "som": "so", "spa": "es", "sqi": "sq", "srp": "sr",
    "swa": "sw", "swe": "sv", "tam": "ta", "tel": "te", "tgk": "tg", "tgl": "tl", "tha": "th", "tuk": "tk",
    "tur": "tr", "ukr": "uk", "urd": "ur", "uzb": "uz", "vie": "vi", "yid": "yi", "yor": "yo", "zho": "zh",
}


class Table:
    """Lookup from any code or name to ISO 639-3, and from ISO 639-3 to 639-1 and a display name."""

    def __init__(self, rows: list[dict]):
        self.to3: dict[str, str] = {}
        self.to1: dict[str, str] = {}
        self.names: dict[str, str] = {}
        for r in rows:
            c3 = (r.get("iso_639_3") or "").lower()
            if not c3:
                continue
            if r.get("iso_639_1"):
                self.to1[c3] = r["iso_639_1"].lower()
            self.names[c3] = r.get("primary_name") or c3
            keys = [r.get("iso_639_1"), r.get("iso_639_2"), c3, r.get("primary_name"),
                    *(r.get("variants") or []), *(r.get("aliases") or [])]
            for k in keys:
                if k:
                    self.to3.setdefault(k.strip().lower(), c3)

    @classmethod
    def builtin(cls) -> "Table":
        return cls([{"iso_639_3": c3, "iso_639_1": c1} for c3, c1 in _TO_1.items()])


@lru_cache(maxsize=1)
def table() -> Table:
    try:
        from .models_repo import languages

        rows = languages()
    except Exception:
        rows = None
    t = Table.builtin()
    if rows:
        shared = Table(rows)
        for attr in ("to3", "to1", "names"):
            getattr(t, attr).update(getattr(shared, attr))
    return t


def norm(code: Optional[str]) -> Optional[str]:
    """Normalise a language code or name to ISO 639-3; unknown codes pass through lowercased."""
    if not code:
        return None
    c = code.strip().lower()
    t = table()
    if c in t.to3:
        return t.to3[c]
    c = c.replace("_", "-").split("-")[0]
    return t.to3.get(c, c)


def iso1(code: Optional[str]) -> Optional[str]:
    """ISO 639-1 for a language, or None when there is none."""
    c = norm(code)
    return table().to1.get(c) if c else None


def name(code: Optional[str]) -> Optional[str]:
    """The English display name of a language (the code itself when unknown)."""
    c = norm(code)
    return table().names.get(c, c) if c else None
