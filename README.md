# LokalReader

**Free, local, non-subscription book reader that speaks books aloud.**

Drop a `.txt`, `.md`, `.pdf`, `.epub`, or `.docx` file into a small local web app. LokalReader splits chapters, guesses fiction vs nonfiction, labels dialogue turns when it can, and narrates with **offline** voices on your machine. No cloud account. No paid TTS API for the default path.

> RVC is a **voice conversion / timbre changer**, not a TTS engine. LokalReader always synthesizes speech with a local TTS backend first, then optionally runs RVC on the resulting WAV.

## Quick start (macOS)

```bash
git clone https://github.com/CourtReinland/LokalReader.git
cd LokalReader
make run
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787).

1. Click **Try the sample scene** (or drop `samples/the_quiet_carriage.txt`)
2. Press **Play**
3. You should hear narration and dialogue on different system / local voices
4. Open **Voices** to remap Narrator / Mara / Eli and save per book

### Requirements

- Python 3.11+ (3.12 fine)
- macOS: built-in `say` (+ `afconvert` when available) — zero extra TTS install
- Linux (dev/CI): `espeak-ng` and `ffmpeg` (`brew install espeak` / `sudo apt install espeak-ng ffmpeg`)

```bash
make test    # parsing, segmentation, TTS smoke tests
make demo    # same as run without reload
```

## What the MVP does

| Feature | Behavior |
|---|---|
| Ingest | `.txt`, `.md`, `.pdf`, `.epub`, `.docx` |
| Chapters | EPUB spine, Markdown headings, `Chapter N` heuristics, PDF page/form-feed splits |
| Fiction detect | Dialogue density, quotation marks, “said/asked…”, chapter cues vs nonfiction cues |
| Segmentation | Narration vs dialogue turns; speakers from `Name said`, `said Name`, `Name:` |
| Editable | Click a segment → change speaker label; mapping UI saves per book |
| Playback | Queues segment WAVs, play/pause/stop, chapter jump, speed control |
| Voices | `LocalTTSBackend` by default; optional `RVCVoiceBackend` post-pass |

## Architecture

```
Book file
  → parsers (txt/md/pdf/epub/docx)
  → chapter split + fiction/nonfiction heuristic
  → segmenter (narration / dialogue + speaker labels)
  → VoiceBackend.synthesize(text, voice_id) → WAV
       ├─ LocalTTSBackend  (macOS say | espeak-ng)
       └─ RVCVoiceBackend  (LocalTTS WAV → optional RVC .pth timbre)
  → browser <audio> queue
```

### VoiceBackend

```python
class VoiceBackend(ABC):
    def list_voices(self) -> list[VoiceInfo]: ...
    def synthesize(self, text, voice_id, out_path, *, speed=1.0) -> Path: ...
```

- **`LocalTTSBackend`** — default, works offline. macOS uses `say -v <Voice> -o file.aiff` then `afconvert`/`ffmpeg` to WAV. Elsewhere uses `espeak-ng` with pitched/rated voice variants so fiction still “sounds different” without RVC.
- **`RVCVoiceBackend`** — wraps LocalTTS, then calls a user-provided infer script with local `assets/weights/*.pth` models. If RVC isn’t configured, it **falls back** to LocalTTS.

## Optional RVC setup

1. Clone and set up [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) on your machine (their docs cover models / GPU).
2. Put character `.pth` files in that project’s `assets/weights/` (or any folder you prefer).
3. Expose an infer CLI that matches LokalReader’s contract (see `scripts/rvc_infer_stub.py`):

```bash
python infer.py --model /path/to/voice.pth --input tts.wav --output character.wav
```

4. Point LokalReader at the install:

```bash
export LOKALREADER_RVC_ROOT=~/src/Retrieval-based-Voice-Conversion-WebUI
export LOKALREADER_RVC_WEIGHTS=$LOKALREADER_RVC_ROOT/assets/weights
export LOKALREADER_RVC_INFER_SCRIPT=/absolute/path/to/your_infer_wrapper.py
export LOKALREADER_RVC_PYTHON=$LOKALREADER_RVC_ROOT/venv/bin/python
make run
```

To dry-run the wiring without GPU models:

```bash
mkdir -p data/rvc_weights
# place or copy a dummy .pth if you want it listed in the UI
export LOKALREADER_RVC_INFER_SCRIPT=$PWD/scripts/rvc_infer_stub.py
export LOKALREADER_RVC_WEIGHTS=$PWD/data/rvc_weights
```

The stub copies the TTS wav through unchanged so you can verify the pipeline.

## Project layout

```
backend/lokalreader/     FastAPI app, parsers, segmentation, voices
frontend/                Local web UI
samples/                 Fiction + nonfiction demos
scripts/rvc_infer_stub.py
tests/
Makefile                 make install | run | test | demo
```

Data (books, cached WAVs, voice mappings) lives under `data/` locally and is gitignored.

## Roadmap

- **Desktop shell** — wrap this web UI with [Tauri](https://tauri.app/) (preferred, lighter) or Electron; keep the Python backend as a sidecar or migrate hot paths later.
- **Better diarization** — optional local LLM / onnx speaker model; heuristics stay the default.
- **Piper / other offline TTS** — higher quality neural voices vendored cleanly.
- **Real RVC presets** — one-click character packs once users drop `.pth` files in.
- **iOS** — future; not in scope for this MVP.
- **DOC legacy `.doc`** — convert externally; `.docx` is supported.

## Test plan (manual)

1. `make run` on a Mac.
2. Open the app → **Try the sample scene**.
3. Confirm the book is labeled **fiction**, with speakers such as Mara / Eli visible.
4. Press Play — narration and dialogue should use different voices.
5. Open **Voices**, change Eli’s voice, Save, Stop, Play again from a dialogue line.
6. Drop `samples/nonfiction_note.md` — should be **nonfiction**, single narrator voice.
7. (Optional) Configure RVC env vars, place a `.pth`, enable “Prefer RVC”, confirm `/api/voices` lists `rvc:…` entries.

Automated: `make test`.

## License

MIT — see [LICENSE](LICENSE).
