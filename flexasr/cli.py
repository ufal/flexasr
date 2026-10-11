"""Command line: run, stage, write, info, models."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import __version__, catalog, langs
from .doc import Doc
from .hardware import detect
from .pipeline import ALL_STAGES, Settings, load_config, run
from .registry import status
from .writers import teitok


def _kv(items, what):
    out = {}
    for it in items or []:
        if "=" not in it:
            raise SystemExit(f"--{what} expects stage=value, got {it!r}")
        k, v = it.split("=", 1)
        out[k.strip()] = v.strip()
    return out


def _opts(items):
    out: dict[str, dict] = {}
    for it in items or []:
        k, _, v = it.partition("=")
        stage, _, key = k.partition(".")
        if not key:
            raise SystemExit(f"--opt expects stage.key=value, got {it!r}")
        try:
            val = json.loads(v)
        except json.JSONDecodeError:
            val = v
        out.setdefault(stage, {})[key] = val
    return out


def _settings(a) -> Settings:
    cfg = load_config()
    smap = json.loads(Path(a.speaker_map).read_text(encoding="utf-8")) if getattr(a, "speaker_map", None) else {}
    mn = mx = None
    if a.speakers and "-" in a.speakers:
        lo, hi = a.speakers.split("-", 1)
        mn, mx = int(lo), int(hi)
    num = int(a.speakers) if a.speakers and "-" not in a.speakers else None
    return Settings(
        language=a.lang, mode=a.mode,
        allow_restricted=a.allow_restricted or bool(cfg.get("allow_restricted")),
        providers=_kv(a.provider, "provider"), models=_kv(a.model, "model"), options=_opts(a.opt),
        num_speakers=num, min_speakers=mn, max_speakers=mx, speaker_map=smap,
        untokenized_roles=tuple(r for r in (a.untokenized_roles or "").split(",") if r),
        keep_dir=Path(a.keep) if a.keep else None,
    )


def _common(p):
    p.add_argument("-l", "--lang", help="language (ISO 639-3 or 639-1); default: detected")
    p.add_argument("--mode", choices=("clean", "verbatim"), default="clean",
                   help="verbatim keeps disfluencies (TEITOK spoken encoding)")
    p.add_argument("--speakers", help="number of speakers, or a range like 2-4")
    p.add_argument("--speaker-map", help="JSON: diarization label → {id, name, role}")
    p.add_argument("--untokenized-roles", help="roles transcribed without <tok>s, e.g. interviewer")
    p.add_argument("--provider", action="append", help="stage=provider (override the router)")
    p.add_argument("--model", action="append", help="stage=catalog-id (override the router)")
    p.add_argument("--opt", action="append", help="stage.key=value provider option (JSON values)")
    p.add_argument("--allow-restricted", action="store_true",
                   help="allow models with restricted licences (e.g. non-commercial); see `flexasr models`")
    p.add_argument("--keep", help="directory to save the intermediate document after every stage")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="flexasr", description="Modular ASR pipeline for TEITOK corpora")
    ap.add_argument("--version", action="version", version=f"flexasr {__version__}")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("run", help="audio → TEITOK XML (or the intermediate JSON)")
    p.add_argument("audio")
    p.add_argument("-o", "--output", help="output file (.xml: TEITOK, .json: intermediate document)")
    _common(p)

    p = sub.add_parser("stage", help="run stages on a saved intermediate document")
    p.add_argument("doc", help="intermediate JSON (flexasr-doc/1)")
    p.add_argument("stages", help=f"comma-separated, from: {','.join(ALL_STAGES)}")
    p.add_argument("-o", "--output", required=True)
    _common(p)

    p = sub.add_parser("write", help="intermediate JSON → TEITOK XML")
    p.add_argument("doc")
    p.add_argument("-o", "--output", required=True)

    sub.add_parser("info", help="hardware, and which providers can run here (and why not)")

    p = sub.add_parser("setup", help="guided access to a gated model (account, token, conditions), then download")
    p.add_argument("model", help="catalog id, e.g. pyannote-community-1")
    p.add_argument("--check", action="store_true", help="only report what is missing (no questions)")
    p.add_argument("--no-download", action="store_true")

    p = sub.add_parser("models", help="catalog entries, and what the router would choose")
    p.add_argument("--task")
    p.add_argument("-l", "--lang")
    p.add_argument("--mode", choices=("clean", "verbatim"), default="clean")
    p.add_argument("--allow-restricted", action="store_true")

    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if a.verbose else logging.INFO, format="%(message)s")
    from .cache import setup as setup_cache

    mdir = setup_cache(load_config())        # downloads go to models_dir (before model libraries load)

    if a.cmd == "info":
        hw = detect()
        print(f"flexasr {__version__}; devices: {', '.join(hw.devices)}"
              + (f" (CUDA {hw.cuda_vram_gb} GB)" if hw.cuda_vram_gb else "")
              + f"; models: {mdir or 'library defaults (set models_dir)'}")
        from . import models_repo

        reached = models_repo.asr_entries() is not None
        print(f"model registry: {models_repo.base_url()}"
              + ("" if reached else " (not reachable: using the bundled snapshot)"))
        for r, av in status(hw):
            mark = "ok " if av.usable else "-- "
            where = f"on {av.device}" if av.usable else av.reason
            print(f"  {mark}{r.spec.name:16} {','.join(r.spec.tasks):12} {where}")
        return 0

    if a.cmd == "models":
        entries = catalog.load()
        lang = langs.norm(a.lang)
        for e in sorted(entries.values(), key=lambda e: (e.task, -e.priority)):
            if a.task and e.task != a.task:
                continue
            flags = [f for f in (("restricted: " + ",".join(e.restricted)) if e.restricted else "",
                                 "gated" if e.gated else "",
                                 "" if e.licence_verified else "licence unverified") if f]
            print(f"{e.task:10} {e.id:26} {e.licence or '?':18} {','.join(e.languages):12} "
                  f"{','.join(e.modes):15} {'; '.join(flags)}")
        print()
        for task in ("diarize", "transcribe", "align"):
            if a.task and task != a.task:
                continue
            try:
                ch = catalog.choose(task, lang, a.mode, allow_restricted=a.allow_restricted, entries=entries)
                print(f"{task}: {ch.entry.id if ch.entry else ch.provider.spec.name} on {ch.device}"
                      + (f"  ({'; '.join(ch.notes)})" if ch.notes else ""))
            except catalog.NoChoice as e:
                print(f"{task}: none usable — {e}")
        return 0

    if a.cmd == "setup":
        from . import access

        entries = catalog.load()
        if a.model not in entries:
            raise SystemExit(f"unknown catalog id {a.model!r}; see `flexasr models`")
        ok = access.setup(entries[a.model], interactive=not a.check, download=not (a.no_download or a.check))
        return 0 if ok else 1

    if a.cmd == "write":
        doc = Doc.from_json(Path(a.doc).read_text(encoding="utf-8"))
        teitok.write(doc, a.output)
        return 0

    s = _settings(a)
    if a.cmd == "run":
        doc = run(a.audio, s)
    else:
        doc = Doc.from_json(Path(a.doc).read_text(encoding="utf-8"))
        doc = run(doc.audio.path, s, stages=tuple(x for x in a.stages.split(",") if x), doc=doc)
    out = a.output
    if not out:
        print(doc.to_json())
    elif out.endswith(".json"):
        Path(out).write_text(doc.to_json(), encoding="utf-8")
    else:
        teitok.write(doc, out)
    return 0


def run_cli():
    try:
        sys.exit(main())
    except catalog.NoChoice as e:
        print(f"flexasr: {e}", file=sys.stderr)
        sys.exit(2)
