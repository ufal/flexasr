"""NVIDIA's Parakeet and Canary models (NeMo) through onnx-asr: onnxruntime only, no PyTorch and no NeMo.

One provider for the family: the models are catalog entries (their ONNX exports on Hugging Face, pinned to a revision,
CC-BY-4.0), not code. They give clean text with punctuation and capitals (no fillers, repetitions or false starts:
mode "clean" only), 25 European languages, and word times from the token times (80 ms resolution) for Parakeet; Canary gives text and
probabilities but no token times in onnx-asr, so its words are timed by the align stage (forced alignment).

Long recordings are cut at long pauses into chunks of at most about 20 s (Silero VAD, also pinned), because these models
decode at most 20-30 s at a time and do badly on short snippets: the VAD settings of onnx-asr's own default give
segments of a second or less, with which a whole sentence can come out empty. Options (catalog entry or ``--opt``):
``quantization`` (default int8 on CPU: the same text at half the time; ``null`` for the full-precision files),
``vad`` (the onnx-asr VAD options), ``onnx_model`` (the onnx-asr model name, from the catalog entry),
``batch_size`` (VAD segments decoded together, default 1).

Segments are decoded one at a time by default. onnx-asr pads the segments of a batch to the longest, and with
Parakeet that changes the text of the shorter ones: on a 1974 tape (NURC) a batch of 8 gave 108 words for two
minutes where one at a time gave about 270, and the same segment came out differently depending on its
neighbours in the batch (once empty). On the CPU, batching gains little.
"""

from __future__ import annotations

import logging

from .. import langs
from ..doc import Utterance
from ._subwords import words_from_tokens
from ._words import utterances_from_words
from .base import ProviderSpec, Transcriber

log = logging.getLogger("flexasr")

# onnx-asr's Silero VAD export, pinned like a model (MIT)
VAD_REPO = "istupakov/silero-vad-onnx"
VAD_REVISION = "b3e3ee3cce4c11ceb63b1a0b229d916069c1ddf6"
VAD_DEFAULTS = {"min_silence_duration_ms": 1500, "max_speech_duration_s": 25, "speech_pad_ms": 300}


class OnnxAsr(Transcriber):
    spec = ProviderSpec(
        name="onnx-asr", family="nemo-onnx", tasks=("transcribe",),
        modes=("clean",), timestamps="word",
        devices=("cuda", "cpu"),
        requires=("onnx_asr", "onnxruntime", "huggingface_hub"),
        description="NVIDIA Parakeet and Canary on onnxruntime (no PyTorch): punctuated clean text, 25 European languages.",
    )

    def version(self):
        from importlib.metadata import version

        return "onnx-asr " + version("onnx-asr")

    def _quantization(self):
        o = self.ctx.options
        if "quantization" in o:
            return o["quantization"] or None
        return "int8" if self.ctx.device != "cuda" else None

    def _providers(self):
        import onnxruntime as ort

        if self.ctx.device == "cuda":
            if "CUDAExecutionProvider" in ort.get_available_providers():
                return ["CUDAExecutionProvider", "CPUExecutionProvider"]
            log.warning("onnxruntime has no CUDA support here (install onnxruntime-gpu): running on the CPU")
        return ["CPUExecutionProvider"]       # CoreML and the like are left out: they print warnings and give no gain

    def _model_dir(self, quantization):
        from huggingface_hub import snapshot_download

        e = self.ctx.entry
        if not e or not (e.source or "").startswith("hf:"):
            raise RuntimeError("onnx-asr needs a catalog entry with an hf: source")
        files = ["*.json", "*.txt", "*.model"]
        if quantization:
            allow, ignore = files + [f"*.{quantization}.onnx"], None
        else:
            allow, ignore = files + ["*.onnx", "*.onnx.data"], [f"*.{q}.onnx" for q in ("int8", "uint8", "fp16", "q4", "q8")]
        return snapshot_download(e.source[3:], revision=e.revision, allow_patterns=allow, ignore_patterns=ignore)

    def transcribe(self, audio, sr, doc):
        import onnx_asr
        import onnxruntime as ort
        from huggingface_hub import snapshot_download

        ort.set_default_logger_severity(3)
        q, prov = self._quantization(), self._providers()
        name = self.ctx.options.get("onnx_model")
        if not name:
            raise RuntimeError("the catalog entry has no onnx_model option (the onnx-asr model name)")
        model = onnx_asr.load_model(name, path=self._model_dir(q), quantization=q, providers=prov)
        vad = onnx_asr.load_vad("silero", path=snapshot_download(VAD_REPO, revision=VAD_REVISION), providers=prov)
        vopts = {**VAD_DEFAULTS, **dict(self.ctx.options.get("vad", {}))}
        kw = {}
        lang = langs.iso1(self.ctx.language)
        if name.startswith("nemo-canary") and lang:
            kw["language"] = lang                   # Canary is told the language; Parakeet v3 finds it itself
        words, chunks = [], []
        batch = int(self.ctx.options.get("batch_size", 1))
        for seg in model.with_vad(vad, batch_size=batch, **vopts).with_timestamps().recognize(audio, sample_rate=sr, **kw):
            if not seg.tokens:
                continue
            w = words_from_tokens(seg.tokens, seg.timestamps, seg.logprobs, offset=seg.start, limit=seg.end)
            words += w
            chunks.append((seg.start, seg.end, w, seg.timestamps is not None))
        if chunks and all(timed for *_, timed in chunks):
            return utterances_from_words(words, float(self.ctx.options.get("utterance_gap", 1.0)))
        # no token times (Canary): one utterance per chunk with words without times; the align stage places them
        return [Utterance(id=f"s{n}", start=round(a, 3), end=round(b, 3), words=w, text=" ".join(x.text for x in w))
                for n, (a, b, w, _) in enumerate(chunks, 1) if w]


PROVIDER = OnnxAsr
