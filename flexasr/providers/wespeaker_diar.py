"""Diarization with a neural speaker-embedding model (ONNX), e.g. WeSpeaker ResNet34.

One provider for the family of ONNX speaker-embedding models that take 80-dim Kaldi filterbanks
(WeSpeaker; also the embedding pyannote uses): the model is a catalog entry, downloaded like any other
(never shipped). VAD, windows, clustering and turns are shared with the built-in diarizer.
"""

from __future__ import annotations

import numpy as np

from ._clustering import ClusteringDiarizer
from .base import ProviderSpec

_EPS = np.finfo(np.float32).eps


def _kaldi_mel(sr: int, n_fft: int, n_mels: int, low: float = 20.0, high: float = 0.0) -> np.ndarray:
    high = high if high > 0 else sr / 2
    mel = lambda f: 1127.0 * np.log(1.0 + np.asarray(f) / 700.0)  # noqa: E731
    lo, hi = mel(low), mel(high)
    centers = lo + (hi - lo) / (n_mels + 1) * np.arange(n_mels + 2)
    fft_mel = mel(np.arange(n_fft // 2) * sr / n_fft)
    fb = np.zeros((n_mels, n_fft // 2 + 1), np.float32)
    for m in range(n_mels):
        l, c, r = centers[m], centers[m + 1], centers[m + 2]
        up = (fft_mel - l) / (c - l)
        down = (r - fft_mel) / (r - c)
        fb[m, : n_fft // 2] = np.maximum(0.0, np.minimum(up, down))
    return fb


def fbank(audio: np.ndarray, sr: int, n_mels: int = 80) -> np.ndarray:
    """Kaldi-compatible log mel filterbank (25 ms / 10 ms, povey window, no dither) on int16 scale."""
    x = audio.astype(np.float32) * 32768.0
    win, hop, n_fft = int(0.025 * sr), int(0.010 * sr), 512
    if len(x) < win:
        return np.zeros((0, n_mels), np.float32)
    n = 1 + (len(x) - win) // hop
    frames = x[np.arange(win)[None, :] + hop * np.arange(n)[:, None]].astype(np.float64)
    frames -= frames.mean(axis=1, keepdims=True)                       # remove DC offset
    frames[:, 1:] -= 0.97 * frames[:, :-1].copy()                      # pre-emphasis
    frames[:, 0] *= 1 - 0.97
    frames *= (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(win) / (win - 1))) ** 0.85   # povey
    power = np.abs(np.fft.rfft(frames, n_fft)) ** 2
    mel = power @ _kaldi_mel(sr, n_fft, n_mels).T
    return np.log(np.maximum(mel, _EPS)).astype(np.float32)


class OnnxSpeakerDiarizer(ClusteringDiarizer):
    spec = ProviderSpec(
        name="speaker-onnx", family="speaker-embedding-onnx", tasks=("diarize",),
        devices=("cpu", "cuda"), requires=("onnxruntime", "huggingface_hub"),
        description="Clustering diarization on a neural speaker-embedding model (ONNX, e.g. WeSpeaker).",
    )
    clustering = "spectral"        # as WeSpeaker's own diarization recipe (eigengap: no fixed threshold)

    def version(self):
        from importlib.metadata import version

        return "onnxruntime " + version("onnxruntime")

    def _session(self):
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download

        e = self.ctx.entry
        if not e or not (e.source or "").startswith("hf:") or not e.options.get("file"):
            raise RuntimeError("speaker-onnx needs a catalog entry with an hf: source and options.file")
        path = hf_hub_download(e.source[3:], e.options["file"], revision=e.revision)
        if e.sha256.get(e.options["file"]):
            import hashlib

            got = hashlib.sha256(open(path, "rb").read()).hexdigest()
            if got != e.sha256[e.options["file"]]:
                raise RuntimeError(f"checksum mismatch for {e.options['file']} ({got}); refusing to use it")
        prov = ["CUDAExecutionProvider", "CPUExecutionProvider"] if self.ctx.device == "cuda" else ["CPUExecutionProvider"]
        return ort.InferenceSession(path, providers=prov)

    def embed(self, audio, sr, wins):
        sess = self._session()
        name = sess.get_inputs()[0].name
        feats = fbank(audio, sr)
        out = np.zeros((len(wins), sess.get_outputs()[0].shape[-1] or 256), np.float32)
        by_len: dict[int, list[int]] = {}
        for i, (a, b) in enumerate(wins):
            by_len.setdefault(min(b, len(feats)) - a, []).append(i)
        batch = int(self.ctx.options.get("batch", 64))
        for length, idx in by_len.items():
            if length <= 0:
                continue
            for k in range(0, len(idx), batch):
                ids = idx[k:k + batch]
                x = np.stack([feats[wins[i][0]:wins[i][0] + length] for i in ids])
                x = x - x.mean(axis=1, keepdims=True)                   # CMN per window
                out[ids] = sess.run(None, {name: x.astype(np.float32)})[0]
        return out / (np.linalg.norm(out, axis=1, keepdims=True) + 1e-9)


PROVIDER = OnnxSpeakerDiarizer
