# flexasr

A modular speech-recognition pipeline for TEITOK corpora: audio in, timed TEI (TEITOK XML) out, with
speakers, roles and — in verbatim mode — disfluencies in TEITOK's spoken encoding.

```
diarize → transcribe → align → assign speakers → encode (verbatim) → write
```

- **Stages, not models.** Each stage is a small contract; *providers* fulfil them (faster-whisper,
  pyannote, WhisperX alignment, …). The pipeline never names a model.
- **Per-language routing.** A catalog says which model does what for which language and mode; the router
  picks the best one usable on your machine (`flexasr models -l fra --mode verbatim`).
- **Runs on any computer.** Every stage has a CPU path; providers that need CUDA, MPS or a missing
  library are listed as unusable, with the reason (`flexasr info`).
- **Verbatim mode** keeps hesitations, truncations, repetitions and pauses, written as TEITOK's spoken
  elements: `<vocal>`, `<pause>`, `<del reason="…">`, `<incident>`.
- **Intermediate format.** Every stage reads and writes one JSON document (`flexasr-doc/1`), so stages can
  be re-run, resumed (`flexasr stage`), or done by other tools.

## Models and licences

flexasr hosts no models. The catalog records where each model can be downloaded (source, pinned revision,
licence); you download from the source and accept its licence. flexasr's own licence covers the code
only. Models with restricted licences (e.g. non-commercial) are never used unless you allow them
(`--allow-restricted`, or `"allow_restricted": true` in `~/.flexasr/config.json`), and every output
records which model, revision and licence produced each layer.

The model entries live in the models repository shared with flexipipe
([ufal/flexipipe-models](https://github.com/ufal/flexipipe-models), `registries/asr/`), in the same
format as flexipipe's registries. Language codes and names (`nl`, `nld`, `Dutch`, `Nederlands`) come from
that repository's `resources/languages.json`. flexasr caches both for a day and works offline from the
cache, or from a snapshot it ships. To use a local checkout or another copy, set
`{"models_repo": "file:///path/to/checkout"}` in `~/.flexasr/config.json` (or `FLEXASR_MODELS_REPO`).

## Quick start

```bash
pip install -e ".[whisper,pyannote]"
flexasr info
flexasr run interview.wav -l fra --speakers 2 -o interview.xml
flexasr run interview.wav -l fra --mode verbatim --untokenized-roles interviewer \
    --speaker-map speakers.json -o interview.xml
```

`speakers.json` maps diarization labels to ids, names and roles:
`{"SPEAKER_00": {"id": "int", "role": "interviewer"}, "SPEAKER_01": {"id": "inf1", "role": "informant"}}`.
Some models are gated: you must log in to Hugging Face and accept their conditions (pyannote's
speaker diarization, for one). `flexasr setup pyannote-community-1` walks you through it — it opens the
token page and the model page, checks your access, and downloads the model. Until then, flexasr simply
uses the next diarizer it can (and says so), down to treating the recording as one speaker.

Downloaded models go to the library caches, or to one folder of your choice (e.g. a large external
disk): `{"models_dir": "/path/to/models"}` in `~/.flexasr/config.json`.

## Adding a model or provider

- A new model of a known family (e.g. another Whisper fine-tune in CTranslate2 format): an entry in
  `registries/asr/<provider>.json` of the models repository, or, just for you, in
  `~/.flexasr/catalog/*.json` (which overrides entries by id). No code either way.
- A new kind of model: a provider class (see `flexasr/providers/base.py`) in a package that registers it
  under the `flexasr.providers` entry point.

Design: `dev/RESHAPE-2026-10.md` (local).
