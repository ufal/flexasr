"""What this machine can run: devices and a rough memory figure (dev/RESHAPE-2026-10.md §3.5)."""

from __future__ import annotations

import functools
import importlib.util
import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Hardware:
    devices: tuple[str, ...]            # in order of preference, always ending in "cpu"
    cuda_vram_gb: float = 0.0

    def best(self, supported: tuple[str, ...]) -> str | None:
        """The preferred device of this machine among ``supported`` (None: none usable)."""
        for d in self.devices:
            if d in supported:
                return d
        return None


@functools.lru_cache(maxsize=1)
def detect() -> Hardware:
    """CUDA / MPS / CPU, without importing torch when it is not installed."""
    forced = os.environ.get("FLEXASR_DEVICE")
    if forced:
        devs = tuple(d.strip() for d in forced.split(",") if d.strip())
        return Hardware(devices=devs + (() if "cpu" in devs else ("cpu",)))
    devices: list[str] = []
    vram = 0.0
    if importlib.util.find_spec("torch") is not None:
        try:
            import torch  # noqa: PLC0415 — optional dependency

            if torch.cuda.is_available():
                devices.append("cuda")
                vram = torch.cuda.get_device_properties(0).total_memory / 2**30
            if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
                devices.append("mps")
        except Exception:  # a broken torch must not stop CPU-only use
            pass
    devices.append("cpu")
    return Hardware(devices=tuple(devices), cuda_vram_gb=round(vram, 1))
