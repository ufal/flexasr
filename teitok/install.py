#!/usr/bin/env python3
"""Install the flexasr TEITOK module into a TEITOK *shared* project.

TEITOK looks for an action's page in the project's Sources/, then in the shared project's Sources/,
then in TEITOK's own common/Sources/, so files placed in the shared project work in every corpus
without touching the TEITOK checkout (as flexicorp's install-teitok-ui.pl does):

    teitok/*.php (not *-test.php)  ->  SHARED/Sources/

Re-running upgrades in place. A manifest (SHARED/Resources/flexasr-teitok.json) records what was
installed, with checksums; a file changed locally since the last install (or there before the first)
is kept as FILE.local-YYYYmmdd-HHMMSS before it is replaced.

    sudo python3 teitok/install.py [--shared DIR] [--user USER] [--dry-run]

Then point the module at flexasr in the corpus (or shared) settings.xml:
    <flexasr bin="/path/to/venv/bin/flexasr" home="/path/to/flexasr-home" models_dir="/big/disk/models"/>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = "Resources/flexasr-teitok.json"


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def files() -> list[Path]:
    return sorted(p for p in HERE.glob("*.php") if not p.name.endswith("-test.php"))


def install(shared: Path, user: str | None, dry: bool) -> int:
    if not (shared / "Sources").is_dir() and not dry:
        (shared / "Sources").mkdir(parents=True)
    man_path = shared / MANIFEST
    old = json.loads(man_path.read_text()) if man_path.is_file() else {"files": {}}
    new = {"tool": "flexasr", "installed": time.strftime("%Y-%m-%dT%H:%M:%S"), "files": {}}
    stamp = time.strftime("%Y%m%d-%H%M%S")
    for src in files():
        rel = f"Sources/{src.name}"
        dst = shared / rel
        h = sha256(src)
        new["files"][rel] = h
        if dst.is_file() and sha256(dst) == h:
            print(f"  unchanged  {rel}")
            continue
        if dst.is_file() and sha256(dst) != old["files"].get(rel):
            backup = dst.with_name(f"{dst.name}.local-{stamp}")
            print(f"  keep local {rel} -> {backup.name}")
            if not dry:
                shutil.copy2(dst, backup)
        print(f"  {'update' if dst.exists() else 'install':10} {rel}")
        if not dry:
            shutil.copy2(src, dst)
            if user:
                shutil.chown(dst, user=user)
    if not dry:
        man_path.parent.mkdir(parents=True, exist_ok=True)
        man_path.write_text(json.dumps(new, indent=1))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--shared", default="/var/www/html/teitok/shared", help="the TEITOK shared project")
    ap.add_argument("--user", help="owner of the installed files (e.g. www-data)")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    shared = Path(a.shared)
    if not shared.is_dir():
        raise SystemExit(f"{shared}: not a directory (give the TEITOK shared project with --shared)")
    print(f"flexasr TEITOK module -> {shared}{' (dry run)' if a.dry_run else ''}")
    return install(shared, a.user, a.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
