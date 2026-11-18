#!/usr/bin/env python3
"""Preview the flexasr TEITOK module locally, without TEITOK and without a login.

    python3 scripts/teitok_preview.py [--port 8099] [--dir DIR] [--bin PATH]

Builds a small sample corpus in DIR (default: a folder under the system temp directory) with audio files that
are open, in progress, and already in a TEITOK file, then serves the module with PHP's built-in server:
http://127.0.0.1:PORT/index.php?action=flexasr   (needs `php` on the PATH). Tasks started from the page run the
real flexasr (--bin, else $FLEXASR_BIN, else `flexasr`) on the files in DIR; nothing else is touched.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
FIXTURE = HERE.parent / "data" / "fixtures" / "interview-fr-tts.wav"


def sample_project(proj: Path) -> None:
    (proj / "Audio").mkdir(parents=True, exist_ok=True)
    (proj / "xmlfiles").mkdir(exist_ok=True)
    jobs = proj / "tmp" / "flexasr-jobs"
    jobs.mkdir(parents=True, exist_ok=True)
    if FIXTURE.exists():
        for name in ("entrevista_nueva.wav", "interview-fr-tts.wav"):
            shutil.copy(FIXTURE, proj / "Audio" / name)
    accent = unicodedata.normalize("NFD", "Extrait_à_transcrire_MEHHA_16oct.mp3")      # as a Mac stores it
    for name in ("COLESFRAN-1.m4a", accent, "argentina_buenos_aires.wav", "I3_corto.m4a"):
        (proj / "Audio" / name).write_bytes(b"")
    tei = '<TEI><teiHeader><recordingStmt><recording><media url="{}"/></recording></recordingStmt></teiHeader></TEI>'
    for name, url in (("COLESFRAN-1", "Audio/COLESFRAN-1.m4a"),
                      ("Extrait", "Audio/" + unicodedata.normalize("NFC", "Extrait_à_transcrire_MEHHA_16oct.mp3")),
                      ("argentina_buenos_aires", "argentina_buenos_aires.wav")):
        (proj / "xmlfiles" / f"{name}.xml").write_text(tei.format(url), encoding="utf-8")
    spec = {"id": "20261118-demo1", "audio": "Audio/I3_corto.m4a", "user": "someone@example.org",
            "started": "2026-11-18T11:00:00+01:00", "fid": "I3_corto", "output": "xmlfiles/I3_corto.xml",
            "lang": "fra", "mode": "verbatim"}
    (jobs / "20261118-demo1.json").write_text(json.dumps(spec), encoding="utf-8")
    (jobs / "20261118-demo1.status").write_text("running\n", encoding="utf-8")
    (jobs / "locks").mkdir(exist_ok=True)       # the lock a started task holds on its audio file
    lock = {"key": "I3_corto.m4a", "job": "20261118-demo1", "user": spec["user"], "since": spec["started"]}
    (jobs / "locks" / (hashlib.md5(b"I3_corto.m4a").hexdigest() + ".lock")).write_text(json.dumps(lock), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--port", type=int, default=8099)
    ap.add_argument("--dir", default=str(Path(tempfile.gettempdir()) / "flexasr-teitok-preview"))
    ap.add_argument("--bin", default=os.environ.get("FLEXASR_BIN", "flexasr"))
    a = ap.parse_args()
    if not shutil.which("php"):
        print("php is needed (the module is PHP): install it, e.g. `brew install php`", file=sys.stderr)
        return 1
    proj = Path(a.dir)
    if not (proj / "xmlfiles").exists():
        sample_project(proj)
    env = {**os.environ, "FA_PREVIEW_PROJ": str(proj), "FA_BIN": a.bin, "FA_RESTRICTED": "1", "FA_LANGUAGE": "fra"}
    print(f"flexasr TEITOK module preview: http://127.0.0.1:{a.port}/index.php?action=flexasr   (project: {proj})", flush=True)
    return subprocess.call(["php", "-S", f"127.0.0.1:{a.port}", str(HERE / "teitok_preview" / "router.php")], env=env)


if __name__ == "__main__":
    sys.exit(main())
