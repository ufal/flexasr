"""Refresh flexasr/catalog/registry-snapshot.json from the shared models repository.

    python scripts/sync_registry_snapshot.py [REPO_URL]

REPO_URL defaults to the configured models_repo (an https URL or file:///path/to/checkout). The snapshot
is only the offline fallback for a first run; the repository itself is the source of the entries.
"""

import json
import sys
from pathlib import Path

from flexasr import models_repo

OUT = Path(__file__).resolve().parent.parent / "flexasr" / "catalog" / "registry-snapshot.json"


def main(argv: list[str]) -> int:
    base = argv[1] if len(argv) > 1 else models_repo.base_url()
    entries = models_repo.asr_entries(base)
    if not entries:
        print(f"no ASR registry found at {base}", file=sys.stderr)
        return 1
    doc = {"comment": "Snapshot of registries/asr from the shared models repository (offline fallback; "
                      "regenerate with scripts/sync_registry_snapshot.py).", "models": entries}
    OUT.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"{len(entries)} entries from {base} → {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
