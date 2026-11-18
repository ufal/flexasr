"""Keep the model libraries' own chatter out of flexasr's log.

transformers, huggingface_hub and tqdm print progress bars, deprecation notices and per-chunk generation
warnings; in a task log (the TEITOK module shows it) they bury flexasr's own progress lines. Set before those
libraries are imported, like the cache locations (cache.py). ``flexasr -v`` (or FLEXASR_LIBS_VERBOSE=1) leaves
them on, for debugging a model.
"""

from __future__ import annotations

import logging
import os
import warnings


def quiet(verbose: bool = False) -> None:
    if verbose or os.environ.get("FLEXASR_LIBS_VERBOSE") or logging.getLogger("flexasr").isEnabledFor(logging.DEBUG):
        return
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("TQDM_DISABLE", "1")
    for pattern in (r".*torch_dtype.*", r".*torchcodec.*", r".*max_new_tokens.*", r".*generation flags.*"):
        warnings.filterwarnings("ignore", message=pattern)
