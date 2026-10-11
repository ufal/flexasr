"""Fetch a JSON file from an http(s) or file URL, with a local cache.

Used for the shared models repository (registries, languages.json): a fresh cached copy is used as
is; otherwise the URL is fetched and cached, and when that fails (offline, not published yet) a stale
cached copy is used. Returns None when there is nothing at all, so callers fall back to bundled data.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import unquote, urlparse

from .home import user_dir

log = logging.getLogger(__name__)
MAX_AGE = 24 * 3600


def cache_dir() -> Path:
    return user_dir() / "cache"


def _read_url(url: str, timeout: float) -> Any:
    u = urlparse(url)
    if u.scheme in ("", "file"):
        return json.loads(Path(unquote(u.path)).read_text(encoding="utf-8"))
    from urllib.request import Request, urlopen

    with urlopen(Request(url, headers={"User-Agent": "flexasr"}), timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _cache_path(url: str) -> Path:
    import hashlib

    name = Path(urlparse(url).path).name or "index"
    return cache_dir() / f"{hashlib.sha1(url.encode()).hexdigest()[:12]}-{name}"


def fetch_json(url: str, max_age: float = MAX_AGE, timeout: float = 10.0) -> Optional[Any]:
    """The JSON at ``url`` (cached for ``max_age`` seconds; local files are always read directly)."""
    if urlparse(url).scheme in ("", "file"):
        try:
            return _read_url(url, timeout)
        except Exception as e:
            log.debug("cannot read %s: %s", url, e)
            return None
    p = _cache_path(url)
    if p.is_file() and time.time() - p.stat().st_mtime < max_age:
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    try:
        data = _read_url(url, timeout)
    except Exception as e:
        log.debug("cannot fetch %s: %s", url, e)
        try:
            return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else None
        except Exception:
            return None
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data
