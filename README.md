# LokalReader

**Free, local, non-subscription book reader that speaks books aloud — with artistic RVC character voices.**

Drop a `.txt`, `.md`, `.pdf`, `.epub`, or `.docx` file into a small local web app. LokalReader splits chapters, guesses fiction vs nonfiction, labels dialogue turns when it can, and narrates with an **offline** pipeline on your machine:

**text → Piper neural TTS → RVC timbre conversion → playback**

No cloud TTS account. No macOS `say` / Samantha. No paid API for the default path.

> **RVC is a voice conversion / timbre changer, not a TTS engine.** It cannot synthesize speech from text. LokalReader always runs Piper first, then converts the WAV with a local `.pth` model.

## Quick start (macOS / Apple Silicon)

```bash
git clone https://github.com/CourtReinland/LokalReader.git
cd LokalReader

# One-time: Piper voices + Python 3.12 RVC venv + HuBERT/RMVPE
# Optional: DOWNLOAD_STARTERS=1 also fetches recommended .pth models from Hugging Face
make setup-voices
# make setup-voices DOWNLOAD_STARTERS=1

make run
```

Open [http://127.0.0.1:8787](http://127.0.0.1:8787).

1. Click **Try the sample scene** (or drop `samples/the_quiet_carriage.txt`)
2. Open **Voices** — assign `rvc:narrator`, `rvc:young_female`, … to Narrator / characters
3. Press **Play** — you should hear Piper→RVC audio (or a loud setup error naming exactly what’s missing)

### Requirements

- Python **3.11+** for the FastAPI app (3.12 fine)
- Python **3.12** for the RVC subprocess (`brew install python@3.12`)
- `ffmpeg` (`brew install ffmpeg`)
- Apple Silicon: CPU/MPS-friendly RVC deps (no NVIDIA CUDA required)

```bash
make test    # Piper + RVC stub wiring tests (CI)
make demo    # same as run without reload
```

## Voice pipeline

```
Book file
  → parsers (txt/md/pdf/epub/docx)
  → chapter split + fiction/nonfiction heuristic
  → segmenter (narration / dialogue + speaker labels)
  → PiperTTSBackend.synthesize(text) → WAV
  → RVCVoiceBackend (Python 3.12 subprocess → python -m infer.cli)
       loads .pth (+ optional .index), hubert + rmvpe
  → browser <audio> queue
```

| Piece | Role |
|---|---|
| **Piper** | Local neural TTS (ONNX). Source speech for RVC. |
| **RVC WebUI** | [Retrieval-based-Voice-Conversion-WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) — timbre convert |
| **`.pth` models** | Character voices in `data/rvc_weights/` listed as `rvc:<name>` |

macOS system voices and espeak are **not** listed in `/api/voices` and are never used on the default synthesize path. Prefer a clear `make setup-voices` error over speaking with Samantha.

### Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `LOKALREADER_RVC_ROOT` | `.rvc/Retrieval-based-Voice-Conversion-WebUI` | RVC WebUI checkout |
| `LOKALREADER_RVC_VENV` | `.venv-rvc` | Python 3.12 venv for RVC |
| `LOKALREADER_RVC_PYTHON` | `.venv-rvc/bin/python` | Interpreter for infer |
| `LOKALREADER_RVC_WEIGHTS` | `data/rvc_weights` | Character `.pth` / `.index` |
| `LOKALREADER_PIPER_VOICES` | `data/piper_voices` | Piper `.onnx` voices |
| `LOKALREADER_RVC_INFER_SCRIPT` | `scripts/rvc_infer.py` | Bridge to `python -m infer.cli` |
| `LOKALREADER_RVC_USE_INDEX` | off | If `1`, pass FAISS `.index` / `--index-rate` (can SIGSEGV on Apple Silicon) |
| `LOKALREADER_ALLOW_EMERGENCY_TTS` | off | If `1`, expose labeled `piper:*` emergency voices (CI/dev only) |

`make setup-voices` writes `.rvc/env.sh`; `make run` sources it when present.

```bash
# After setup, always load the RVC env before run (or rely on make run):
source .rvc/env.sh
make run
```

### Troubleshooting RVC

#### `No module named 'infer'`

`scripts/rvc_infer.py` must invoke RVC as a package from the WebUI checkout:

- cwd = `LOKALREADER_RVC_ROOT`
- `PYTHONPATH` prepends that root
- command = `$LOKALREADER_RVC_PYTHON -m infer.cli …` (not `python infer/cli.py`)

If you still see import errors, confirm:

```bash
source .rvc/env.sh
echo "$LOKALREADER_RVC_ROOT" "$LOKALREADER_RVC_PYTHON"
"$LOKALREADER_RVC_PYTHON" -c "import sys; sys.path.insert(0, '$LOKALREADER_RVC_ROOT'); import infer.cli; print('infer ok')"
```

#### Apple Silicon FAISS segfault (exit 139)

On Apple Silicon, `faiss-cpu` index retrieval can crash the RVC subprocess (`SIGSEGV` / exit 139) when `--index` / `--index-rate 0.75` is used. LokalReader **defaults to `--index-rate 0`** (timbre conversion still works with `pm` or `rmvpe`). Only enable retrieval if you know your faiss build is stable:

```bash
export LOKALREADER_RVC_USE_INDEX=1   # opt-in; may crash on Mac
```

Further dependency errors (torch, hubert, rmvpe) are reported in the API toast — re-run `make setup-voices` if assets are missing.

## Starter character voices

Suggested files in `data/rvc_weights/`:

| File | Role |
|---|---|
| `narrator.pth` | Narrator |
| `young_female.pth` | Younger female dialogue |
| `young_male.pth` | Younger male dialogue |
| `older_narrator.pth` | Older narrator |

Optional sidecar JSON (auto-written by the download script):

```json
{ "role": "narrator", "gender": "male", "description": "Steady fiction narrator" }
```

Community `.pth` models often have unclear redistribution rights, so they are **not** vendored in git. See `data/rvc_weights/voices.manifest.json` for recommended Hugging Face IDs, then:

```bash
make setup-voices DOWNLOAD_STARTERS=1
# or copy your own .pth files into data/rvc_weights/
```

HuBERT + RMVPE come from [`lj1995/VoiceConversionWebUI`](https://huggingface.co/lj1995/VoiceConversionWebUI) into the RVC checkout (`assets/hubert_base/`, `assets/rmvpe/rmvpe.pt`).

### Custom character (e.g. Raksa)

1. Train/clone a voice in the RVC WebUI (their docs: `docs/en/README.en.md`).
2. Copy `YourVoice.pth` (+ `.index`) into `data/rvc_weights/`.
3. Restart / refresh **Voices** — it appears as `rvc:YourVoice`.
4. Assign it to a character and Save.

## API / UI

- `GET /api/voices` — `rvc:*` catalog + Piper status + RVC subprocess state (`ready` / `missing_models` / setup hints)
- Fiction: map different RVC models to Narrator + each character
- Nonfiction: single narrator voice
- Missing weights/TTS → HTTP 503 with an explicit “run `make setup-voices`” message (shown in the web UI toast)

## Project layout

```
backend/lokalreader/     FastAPI app, parsers, segmentation, voices
  voices/piper_tts.py    Piper neural TTS
  voices/rvc.py          RVC subprocess orchestration
frontend/                Local web UI
samples/                 Fiction + nonfiction demos
scripts/
  setup_voices.sh        make setup-voices
  rvc_infer.py           Bridge → python -m infer.cli (PYTHONPATH=RVC root)
  rvc_infer_stub.py      CI passthrough only (not real conversion)
  download_starter_voices.py
data/rvc_weights/        Your .pth models (gitignored)
data/piper_voices/       Piper ONNX voices (gitignored)
Makefile                 make install | setup-voices | run | test | demo
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
| Voices | Piper → RVC `.pth` characters (no system TTS in the Voices panel) |

## Roadmap

- **Desktop shell** — Tauri (preferred) or Electron; Python backend as sidecar
- **Better diarization** — optional local LLM / onnx speaker model; heuristics stay default
- **iOS** — future; out of scope for this MVP
- **DOC legacy `.doc`** — convert externally; `.docx` is supported

## Test plan (manual)

1. `make setup-voices` (and place or download `.pth` starters).
2. `make run` on a Mac.
3. Open the app → **Try the sample scene**.
4. Confirm **fiction**, speakers such as Mara / Eli visible.
5. **Voices** panel lists `rvc:…` only (no `mac:*`). Piper + RVC status shows ready.
6. Press Play — narration and dialogue use different RVC timbres.
7. Change Eli’s voice, Save, Stop, Play again from a dialogue line.
8. Drop `samples/nonfiction_note.md` — **nonfiction**, single narrator voice.
9. With weights removed, Play must fail with a clear “run `make setup-voices`” style error — never Samantha.

Automated: `make test` (Piper + RVC stub wiring).

## License

MIT — see [LICENSE](LICENSE). RVC and community `.pth` models retain their own licenses.
