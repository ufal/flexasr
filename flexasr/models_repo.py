"""The shared models repository (ufal/flexipipe-models, to become flexitools-models).

flexasr shares it with flexipipe: ASR model entries live in ``registries/asr/<provider>.json`` (listed
in ``registries/asr/index.json``), in the same structure as flexipipe's registries (``version``,
``last_updated``, ``sources`` → ``official`` / ``community`` lists), and language names and codes in
``resources/languages.json``. The repository only records where models come from; it hosts none.

The base URL is ``models_repo`` in ``~/.flexasr/config.json`` or ``$FLEXASR_MODELS_REPO`` (an
https URL, or ``file:///…`` for a local checkout).
"""

from __future__ import annotations

import os
from typing import Any, Optional

from .home import load_config
from .remote import fetch_json

DEFAULT = "https://raw.githubusercontent.com/ufal/flexipipe-models/main"
ASR_DIR = "registries/asr"
SOURCES = ("official", "flexipipe", "community")
# Fields of the shared registry format that flexasr does not keep (it has its own equivalents).
_SHARED_ONLY = ("language_iso", "language_name", "preferred", "curated", "size_mb", "download_command")


def base_url() -> str:
    url = os.environ.get("FLEXASR_MODELS_REPO") or load_config().get("models_repo") or DEFAULT
    return url.rstrip("/")


def to_entry(m: dict[str, Any]) -> dict[str, Any]:
    """A shared-registry model entry → a flexasr catalog entry (as a dict)."""
    e = {k: v for k, v in m.items() if k not in _SHARED_ONLY}
    e["id"] = e.pop("model")
    if "description" in e:
        e["note"] = e.pop("description")
    if "languages" not in e and m.get("language_iso"):
        e["languages"] = [x.strip() for x in str(m["language_iso"]).split(",") if x.strip()]
    return e


def from_entry(e: dict[str, Any]) -> dict[str, Any]:
    """A flexasr catalog entry → a shared-registry model entry (the inverse of :func:`to_entry`)."""
    m = {"model": e["id"], **{k: v for k, v in e.items() if k not in ("id", "note")}}
    if e.get("note"):
        m["description"] = e["note"]
    if m.get("languages", ["*"]) != ["*"]:
        m["language_iso"] = ",".join(m["languages"])
    return m


def registry_entries(data: dict[str, Any]) -> list[dict[str, Any]]:
    return [to_entry(m) for src in SOURCES for m in (data.get("sources") or {}).get(src, [])]


def asr_entries(base: Optional[str] = None) -> Optional[list[dict[str, Any]]]:
    """All ASR entries from the shared repository, or None when it cannot be reached (nor is cached)."""
    base = base or base_url()
    index = fetch_json(f"{base}/{ASR_DIR}/index.json")
    if not index:
        return None
    out: list[dict[str, Any]] = []
    for name in index.get("files", []):
        data = fetch_json(f"{base}/{ASR_DIR}/{name}")
        if data:
            out.extend(registry_entries(data))
    return out


def languages(base: Optional[str] = None) -> Optional[list[dict[str, Any]]]:
    data = fetch_json(f"{base or base_url()}/resources/languages.json")
    return data.get("languages") if isinstance(data, dict) else None
