"""flexasr's per-user directory (``~/.flexasr``, or ``$FLEXASR_HOME``) and its config.json."""

from __future__ import annotations

import json
import os
from pathlib import Path


def user_dir() -> Path:
    return Path(os.environ.get("FLEXASR_HOME", Path.home() / ".flexasr"))


def load_config() -> dict:
    p = user_dir() / "config.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
