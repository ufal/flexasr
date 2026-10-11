"""Finding providers: built-in modules and the ``flexasr.providers`` entry point group."""

from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Optional

from .hardware import Hardware, detect
from .providers.base import Availability, Provider, ProviderSpec, availability

log = logging.getLogger(__name__)


@dataclass
class Registered:
    spec: ProviderSpec
    load: object                      # callable returning the Provider class (lazy import)
    origin: str                       # module or entry point
    error: Optional[str] = None       # why it could not be loaded (shown by `flexasr info`)


_extra: dict[str, Registered] = {}


def register(cls: type[Provider], origin: str = "runtime") -> None:
    """Register a provider class at run time (tests, plugins loaded by hand)."""
    _extra[cls.spec.name] = Registered(cls.spec, lambda c=cls: c, origin)


def _builtin() -> dict[str, Registered]:
    from . import providers as pkg

    out: dict[str, Registered] = {}
    for mod in pkgutil.iter_modules(pkg.__path__):
        if mod.name.startswith("_") or mod.name == "base":
            continue
        name = f"{pkg.__name__}.{mod.name}"
        try:
            m = importlib.import_module(name)
        except Exception as e:  # a provider module must import without its heavy dependencies
            out[mod.name] = Registered(ProviderSpec(mod.name, "?", ()), None, name, f"import failed: {e}")
            continue
        cls = getattr(m, "PROVIDER", None)
        if cls is not None:
            out[cls.spec.name] = Registered(cls.spec, lambda c=cls: c, name)
    return out


def _plugins() -> dict[str, Registered]:
    out: dict[str, Registered] = {}
    for ep in entry_points(group="flexasr.providers"):
        try:
            cls = ep.load()
            out[cls.spec.name] = Registered(cls.spec, lambda c=cls: c, f"entry point {ep.value}")
        except Exception as e:
            out[ep.name] = Registered(ProviderSpec(ep.name, "?", ()), None, f"entry point {ep.value}",
                                      f"load failed: {e}")
    return out


def all_providers() -> dict[str, Registered]:
    reg = _builtin()
    reg.update(_plugins())
    reg.update(_extra)
    return reg


def status(hw: Optional[Hardware] = None) -> list[tuple[Registered, Availability]]:
    """Every provider with whether it can run here (and why not)."""
    hw = hw or detect()
    out = []
    for r in sorted(all_providers().values(), key=lambda r: r.spec.name):
        if r.error:
            out.append((r, Availability(False, r.error)))
        else:
            out.append((r, availability(r.spec, hw)))
    return out


def get(name: str) -> Registered:
    reg = all_providers()
    if name not in reg:
        raise KeyError(f"unknown provider {name!r}; known: {', '.join(sorted(reg))}")
    r = reg[name]
    if r.error:
        raise RuntimeError(f"provider {name!r} is not usable: {r.error}")
    return r
