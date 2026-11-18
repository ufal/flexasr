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
licence); you download from the source and accept its licence. flexasr's own licence (MIT) covers the code
only. Models with restricted licences (e.g. non-commercial) are never used unless you allow them
(`--allow-restricted`, or `"allow_restricted": true` in `~/.flexasr/config.json`), and every output
records which model, revision and licence produced each layer.

Verbatim transcription (fillers, repetitions, false starts) currently comes from CrisperWhisper 2.0
(`pip install -e ".[crisperwhisper]"`). Its licence makes both the weights and **everything they
produce** non-commercial, so it is an optional install (never pulled in by the default install), flexasr
uses it only with `--allow-restricted` (pip cannot show messages while installing, so the licence is shown
before the first download and in `flexasr models`), and the TEI header of the output states the restriction
(`<publicationStmt><availability status="restricted"><licence>…`). The same header note names any model
whose licence differs from flexasr's own. For academic corpora this is normally no problem; check before
any commercial use. Without it, verbatim mode falls back to Whisper and warns that fillers may be lost.

Clean transcription in 25 European languages (Bulgarian, Croatian, Czech, Danish, Dutch, English, Estonian, Finnish,
French, German, Greek, Hungarian, Italian, Latvian, Lithuanian, Maltese, Polish, Portuguese, Romanian, Russian,
Slovak, Slovenian, Spanish, Swedish, Ukrainian) comes from NVIDIA's **Canary-1B-v2** and **Parakeet-TDT-0.6B-v3**
(`pip install -e ".[onnx]"`: onnxruntime only, no PyTorch and no NeMo; CC-BY-4.0, so no restriction on the output).
They give punctuated text without fillers or repetitions (mode `clean` only). Canary is the more accurate and the
default; Parakeet is about four times faster (roughly 40 and 11 times real time on one CPU, int8 files, about 0.7 and
1 GB) and takes its word times from its own tokens (an 80 ms grid: expect a few tenths of a second of looseness;
`--model align=whisperx-wav2vec2` places them by forced alignment); Canary has no token times in onnx-asr, so the
align stage times its words. The speech is cut at pauses of 1.5 s or more into chunks of at most 25 s (a pinned
Silero VAD). For these languages they take the place of Whisper in clean mode; Whisper still covers everything else.

The model entries live in the models repository shared with flexipipe
([ufal/flexipipe-models](https://github.com/ufal/flexipipe-models), `registries/asr/`), in the same
format as flexipipe's registries. Language codes and names (`nl`, `nld`, `Dutch`, `Nederlands`) come from
that repository's `resources/languages.json`. flexasr caches both for a day and works offline from the
cache, or from a snapshot it ships. To use a local checkout or another copy, set
`{"models_repo": "file:///path/to/checkout"}` in `~/.flexasr/config.json` (or `FLEXASR_MODELS_REPO`).

## The `flexasr` command

`flexasr install wrapper` writes a small launcher, so that plain `flexasr …` works whichever Python is active (the way
`flexipipe install wrapper` does): into `/usr/local/bin` when that can be written, else `~/.local/bin`, or where
`--path` says. It runs the environment it was made from, or the one given with `--venv`. The tools of the ecosystem
can share one environment: create it once (`python3 -m venv ~/.flexitools/venv`), install the tools into it, run
`install wrapper` for each, and set `FLEXITOOLS_VENV` to move all of them at once; `FLEXASR_VENV` overrides it for
this tool alone (a tool that needs its own packages can keep its own environment: CrisperWhisper's CTranslate2
fork, for one, cannot live next to the upstream one that faster-whisper needs). A model registry that changed is
fetched at once with `--refresh-cache` (otherwise it is kept for a day).

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

## In TEITOK

`teitok_modules/` holds a TEITOK module (`index.php?action=flexasr`). In it, project members can:

- upload an audio file, or pick one from the corpus's `Audio/` folder, where the files are shown in sections by what is
  left to do: no TEITOK file yet, in progress, and already in a TEITOK file (found through the `<media url>` in
  the header of the `xmlfiles/`, with or without the `Audio/` prefix; whatever tool made that file);
- start a file with its **Transcribe** button; the settings page also asks who the interviewer is (the speaker who
  speaks least or most, or the first or second to speak: transcribed as text, without tokens), at which pauses to
  split utterances (`--split-gap`), and whether to move speaker changes to the nearest pause or sentence end
  (`--no-snap` turns that off; it corrects the words at the edge of a turn, which a diarizer places only roughly);
  and on the next page choose the language, the mode (verbatim or
  clean) and whether restricted models may be offered (the choices below refresh when you change them);
- see which models the router would use and why, override them, and set the number of speakers;
- start the pipeline as a background task, follow its log, and see recent tasks (by the name of whoever started
  them). A file that is being processed holds a lock (`tmp/flexasr-jobs/locks/`), so it cannot be started twice,
  also not by a double click; the lock goes when the task ends, when its process is gone (a crashed or restarted
  server), or when an administrator presses **Stop**, which ends the process and frees the file. A lock can also
  be removed by hand. Without a process to check, a task that has not moved for 12 hours (`stale_hours="…"`)
  counts as stalled;
- work through large collections: the lists show 100 files at a time ("show more" for the next page), with a
  search box, and the files already in a TEITOK file are found by a scan of the `xmlfiles/` headers that runs in
  small steps in the background;
- open the resulting `xmlfiles/<name>.xml` in TEITOK's waveform and text views, with the model, licence
  and any restriction of each step listed.

Install it into the TEITOK shared project and tell it where flexasr is:

```bash
sudo perl teitok_modules/install-flexasr.pl --shared /var/www/html/teitok/shared --user www-data
```

```xml
<flexasr bin="/opt/flexasr/.venv/bin/flexasr" home="/opt/flexasr-home" models_dir="/data/models"
         language="fra" restricted="1"/>
```

`home` is a flexasr home (config, gated-model access) for the web server user; run `flexasr setup`
for gated models with `FLEXASR_HOME` set to it. any staff login (not an SSO login) may use the module, and `admin="1"` limits it to administrators; a task can be stopped by whoever started it or by an administrator; `language` is the default language and `restricted="1"` offers
restricted-licence models by default (for an academic corpus; the licence conditions are shown before a job starts).

### The transcript editor (spoken-edit)

`index.php?action=spoken-edit&cid=FILE` is a keyboard-driven editor for transcripts: utterances with speakers and timed
words, uncertain words marked (when the transcription has confidences), audio playback from any word, split/merge/move of
utterances, speaker changes, full screen (`f`), and a window with all actions and keys (`?`). Edits are saved as splices
of the original XML, so everything else in the file stays byte-for-byte as it was.

It is also a **viewer**: with `<spokenedit public="1"/>` in the project's `settings.xml`, everybody, with or without a login,
gets the same display with the keys for moving, playing and full screen, and no editing. A logged-in user gets the viewer
with `&view=1`. Without `public`, the page needs a staff login, as the flexasr page does.

## Adding a model or provider

- A new model of a known family (e.g. another Whisper fine-tune in CTranslate2 format): an entry in
  `registries/asr/<provider>.json` of the models repository, or, just for you, in
  `~/.flexasr/catalog/*.json` (which overrides entries by id). No code either way.
- A new kind of model: a provider class (see `flexasr/providers/base.py`) in a package that registers it
  under the `flexasr.providers` entry point.

Design: `dev/RESHAPE-2026-10.md` (local).

## License

MIT — see [`LICENSE`](LICENSE). Models keep their own licences (see *Models and licences*).

If you use flexasr in research, please cite it: [`CITATION.cff`](CITATION.cff) has the reference (GitHub shows it as "Cite this repository").
