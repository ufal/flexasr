"""Access to gated models (e.g. pyannote's), with a guided setup.

A gated Hugging Face model needs three things from the user: an account, a token on this machine, and
the model's conditions accepted on its page. Nobody gets that right from a README, so
``flexasr setup <model>`` walks through it (opening the pages, re-checking until it works), and the
router treats a gated model without access as unusable — with "run flexasr setup …" as the reason —
and falls back to another provider instead of failing halfway.
"""

from __future__ import annotations

import json
import time
import webbrowser
from dataclasses import dataclass
from getpass import getpass
from typing import TYPE_CHECKING, Callable, Optional

from .catalog import user_dir

if TYPE_CHECKING:  # pragma: no cover
    from .catalog import Entry

TOKEN_PAGE = "https://huggingface.co/settings/tokens"
JOIN_PAGE = "https://huggingface.co/join"
_OK_DAYS = 7


@dataclass
class Access:
    ok: bool
    reason: str = ""
    step: str = ""            # "token" | "accept" | "network" | "" — what the user has to do


def repos(e: "Entry") -> list[str]:
    """The Hugging Face repos whose conditions must be accepted for ``e``."""
    extra = list(e.options.get("gated_repos", [])) if e.options else []
    main = [e.source[3:]] if (e.source or "").startswith("hf:") else []
    return main + [r for r in extra if r not in main]


def token(explicit: Optional[str] = None) -> Optional[str]:
    import os

    t = explicit or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if t:
        return t
    try:
        from huggingface_hub import get_token

        return get_token()
    except Exception:
        return None


def _cached(repo: str, revision: Optional[str]) -> bool:
    """Already downloaded (works offline, no token needed)?"""
    try:
        from huggingface_hub import snapshot_download

        snapshot_download(repo, revision=revision, local_files_only=True)
        return True
    except Exception:
        return False


def _memo_path():
    return user_dir() / "access.json"


def _memo() -> dict:
    p = _memo_path()
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _remember(repo: str) -> None:
    m = _memo()
    m[repo] = time.time()
    p = _memo_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(m, indent=1), encoding="utf-8")


def check_repo(repo: str, revision: Optional[str] = None, tok: Optional[str] = None,
               use_memo: bool = True) -> Access:
    if _cached(repo, revision):
        return Access(True)
    if use_memo and time.time() - _memo().get(repo, 0) < _OK_DAYS * 86400:
        return Access(True)
    tok = token(tok)
    if not tok:
        return Access(False, "needs a Hugging Face login (token)", "token")
    try:
        from huggingface_hub import auth_check
        from huggingface_hub.errors import GatedRepoError, RepositoryNotFoundError
    except Exception:
        return Access(False, "huggingface_hub is not installed", "")
    try:
        auth_check(repo, token=tok)
    except GatedRepoError:
        return Access(False, f"conditions of {repo} not accepted yet", "accept")
    except RepositoryNotFoundError:
        return Access(False, f"{repo}: not found, or the token has no access", "token")
    except Exception as e:  # offline, timeouts
        return Access(False, f"cannot check access to {repo} ({type(e).__name__}); offline?", "network")
    _remember(repo)
    return Access(True)


def check(e: "Entry", tok: Optional[str] = None) -> Access:
    """Can this (gated) entry be used now? Non-gated entries always can."""
    if not e.gated:
        return Access(True)
    for r in repos(e):
        a = check_repo(r, e.revision, tok)
        if not a.ok:
            return Access(False, f"{a.reason} — run `flexasr setup {e.id}`", a.step)
    return Access(True)


def setup(e: "Entry", interactive: bool = True, say: Callable[[str], None] = print,
          ask: Callable[[str], str] = input, secret: Callable[[str], str] = getpass,
          open_page: Callable[[str], bool] = webbrowser.open, download: bool = True) -> bool:
    """Walk the user through access to ``e`` (account, token, conditions), then optionally download."""
    say(f"Setting up {e.id} ({e.source}, licence {e.licence or '?'})")
    if e.note:
        say(f"  {e.note}")
    if not e.gated:
        say("  This model is not gated: nothing to accept.")
    else:
        for repo in repos(e):
            for attempt in range(3):
                a = check_repo(repo, e.revision, use_memo=False)
                if a.ok:
                    say(f"  ✓ access to {repo}")
                    break
                say(f"  ✗ {a.reason}")
                if not interactive:
                    _explain(a.step, repo, say)
                    break
                if a.step == "token":
                    say(f"  1. Log in or create a free account: {JOIN_PAGE}")
                    say(f"  2. Create a token of type \"Read\": {TOKEN_PAGE}")
                    if ask("     Open the token page in your browser? [Y/n] ").strip().lower() != "n":
                        open_page(TOKEN_PAGE)
                    t = secret("     Paste the token here (it is not shown): ").strip()
                    if t:
                        from huggingface_hub import login

                        login(token=t, add_to_git_credential=False)
                        say("     token saved for this user")
                elif a.step == "accept":
                    page = f"https://huggingface.co/{repo}"
                    say(f"  Open {page}, log in with the same account, and accept the conditions")
                    say("  (\"Agree and access repository\"; some models ask a few questions about your use).")
                    if ask("     Open the page in your browser? [Y/n] ").strip().lower() != "n":
                        open_page(page)
                    ask("     Press Enter when you have accepted … ")
                else:
                    _explain(a.step, repo, say)
                    return False
            else:
                say(f"  Still no access to {repo}; run `flexasr setup {e.id}` again later.")
                return False
            if not check_repo(repo, e.revision, use_memo=False).ok:
                return False
    if download and (e.source or "").startswith("hf:"):
        if not interactive or ask("  Download the model now? [Y/n] ").strip().lower() != "n":
            from huggingface_hub import snapshot_download

            path = snapshot_download(e.source[3:], revision=e.revision, token=token())
            say(f"  ✓ downloaded to {path}")
    say(f"  {e.id} is ready.")
    return True


def _explain(step: str, repo: str, say: Callable[[str], None]) -> None:
    if step == "token":
        say(f"    → log in (free account: {JOIN_PAGE}), create a Read token ({TOKEN_PAGE}),")
        say("      then run `flexasr setup` again, or set HF_TOKEN")
    elif step == "accept":
        say(f"    → accept the conditions on https://huggingface.co/{repo} (same account as the token)")
    elif step == "network":
        say("    → check the internet connection, then run `flexasr setup` again")


def download_notice(e: "Entry") -> Optional[str]:
    """Before a model is downloaded for the first time: where it comes from, its licence and any
    licence note (flexasr only points to the model; the user obtains it under its own licence)."""
    if not (e.source or "").startswith("hf:") or _cached(e.source[3:], e.revision):
        return None
    msg = f"downloading {e.id} from https://huggingface.co/{e.source[3:]} — licence: {e.licence or 'not stated'}"
    if e.restricted:
        msg += " (restricted: " + ", ".join(e.restricted) + ")"
    if getattr(e, "licence_note", ""):
        msg += f". Note: {e.licence_note}"
    return msg
