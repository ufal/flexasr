"""``flexasr install wrapper``: a plain ``flexasr`` command that works whichever Python is active.

The launcher is a small shell script that runs ``python -m flexasr`` with the Python of a virtual environment: the one
this was made in, or another given with ``--venv``. The environment can be changed without writing the launcher again:
``$FLEXASR_VENV`` (this tool) or ``$FLEXITOOLS_VENV`` (all the tools of the ecosystem, which can share one environment)
take precedence over the one that was recorded. Same idea as ``flexipipe install wrapper`` (Unix only).
"""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

NAME = "flexasr"
MARK = f"# written by `{NAME} install wrapper`"


def script(venv: Path) -> str:
    return f"""#!/bin/sh
{MARK}
# The Python it runs: ${NAME.upper()}_VENV, else $FLEXITOOLS_VENV (an environment shared by the ecosystem's tools), else the
# environment this was made in. Change it by setting a variable, or by running `{NAME} install wrapper --force` again.
VENV="${{{NAME.upper()}_VENV:-${{FLEXITOOLS_VENV:-{venv}}}}}"
exec "$VENV/bin/python" -m {NAME} "$@"
"""


def default_dir() -> Path:
    """/usr/local/bin when it can be written (and is on the PATH), else ~/.local/bin."""
    sysdir = Path("/usr/local/bin")
    if sysdir.is_dir() and os.access(sysdir, os.W_OK):
        return sysdir
    return Path.home() / ".local" / "bin"


def _on_path(d: Path) -> bool:
    return str(d) in os.environ.get("PATH", "").split(os.pathsep)


def install(path: Optional[str] = None, venv: Optional[str] = None, force: bool = False,
            out: Callable[[str], None] = print) -> int:
    v = Path(venv).expanduser().resolve() if venv else Path(sys.prefix)
    py = v / "bin" / "python"
    if not py.is_file():
        out(f"{NAME}: no Python at {py} (give the virtual environment with --venv)")
        return 1
    if venv and subprocess.run([str(py), "-c", f"import {NAME}"], capture_output=True).returncode != 0:
        out(f"{NAME}: {NAME} is not installed in {v}")
        return 1
    d = Path(path).expanduser() if path else default_dir()
    target = d / NAME
    if target.exists() or target.is_symlink():
        ours = target.is_file() and not target.is_symlink() and MARK in target.read_text(encoding="utf-8", errors="ignore")
        if not ours and not force:
            what = f"a link to {os.readlink(target)}" if target.is_symlink() else "a file that was not made by this command"
            out(f"{NAME}: {target} is {what}; use --force to replace it")
            return 1
    try:
        d.mkdir(parents=True, exist_ok=True)
        if target.is_symlink():
            target.unlink()
        target.write_text(script(v), encoding="utf-8")
        target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    except OSError as e:
        out(f"{NAME}: cannot write {target}: {e}" + (" (try --path ~/.local/bin, or sudo)" if d == Path('/usr/local/bin') else ""))
        return 1
    out(f"{NAME}: installed {target} (runs {py})")
    if not _on_path(d):
        out(f"{d} is not on the PATH; add it:  echo 'export PATH=\"{d}:$PATH\"' >> ~/.zshrc")
    return 0
