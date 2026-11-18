"""Disk space for model downloads: is a model already downloaded, and does it fit if not?

The router uses this to skip a model whose download cannot fit (saying so) instead of failing halfway
through a multi-GB download; it then falls back to the next model.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:  # pragma: no cover
    from .catalog import Entry

MARGIN_MB = 500                    # room left for temporary files, logs and the corpus


def hub_dir() -> Path:
    """Where Hugging Face downloads go (models_dir/huggingface/hub once cache.setup has run)."""
    if os.environ.get("HF_HUB_CACHE"):
        return Path(os.environ["HF_HUB_CACHE"])
    home = Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface"))
    return home / "hub"


def free_mb(path: Path) -> float:
    p = path
    while not p.exists() and p != p.parent:
        p = p.parent
    return shutil.disk_usage(p).free / 1e6


def cached(repo: str, revision: Optional[str]) -> bool:
    """Already downloaded (works offline, no token needed)?"""
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo, revision=revision, local_files_only=True)
        return True
    except Exception:
        return False


def shortfall(e: "Entry") -> Optional[str]:
    """Why ``e`` cannot be downloaded here for lack of space, or None (fits, cached, or size unknown)."""
    if not e.size_mb or not (e.source or "").startswith("hf:"):
        return None
    if cached(e.source[3:], e.revision):
        return None
    where = hub_dir()
    free = free_mb(where)
    if free >= e.size_mb + MARGIN_MB:
        return None
    return (f"download needs {e.size_mb / 1000:.1f} GB, only {free / 1000:.1f} GB free in {where} "
            f"(set models_dir to a larger disk)")
