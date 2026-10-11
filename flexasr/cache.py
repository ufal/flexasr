"""Where downloaded models go (they are never hosted by flexasr, only downloaded from their source).

``models_dir`` (``~/.flexasr/config.json`` or ``FLEXASR_MODELS``) redirects the download caches of the
libraries the providers use — Hugging Face hub (faster-whisper, pyannote, transformers), torch hub
(torchaudio / WhisperX alignment models), CrisperWhisper's converted models — to one place, e.g. a large external disk. It must be set up
before those libraries are imported: they read their cache location at import time.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

log = logging.getLogger("flexasr")


def models_dir(config: Optional[dict] = None) -> Optional[Path]:
    v = os.environ.get("FLEXASR_MODELS") or (config or {}).get("models_dir")
    return Path(v).expanduser() if v else None


def setup(config: Optional[dict] = None) -> Optional[Path]:
    """Point the download caches at ``models_dir`` (no-op when unset). Returns the directory."""
    d = models_dir(config)
    if d is None:
        return None
    if not d.parent.exists():
        raise RuntimeError(f"models_dir {d} is not reachable (is the disk mounted?)")
    hub, torch_home = d / "huggingface" / "hub", d / "torch"
    hub.mkdir(parents=True, exist_ok=True)
    torch_home.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("HF_HUB_CACHE", str(hub))
    os.environ.setdefault("TORCH_HOME", str(torch_home))
    os.environ.setdefault("CRISPERWHISPER_CACHE", str(d / "crisperwhisper"))
    if "huggingface_hub" in sys.modules:
        from huggingface_hub import constants

        if Path(constants.HF_HUB_CACHE) != hub:
            log.warning("huggingface_hub was imported before the models_dir setup; downloads may go to %s",
                        constants.HF_HUB_CACHE)
    return d
