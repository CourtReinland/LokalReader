# RVC character weights

Drop RVC v2 `.pth` models (and optional `.index` files) here. LokalReader lists them as `rvc:<stem>` voices.

## Suggested starter set (fiction)

| File | Role | Gender |
|---|---|---|
| `narrator.pth` | Narrator | male |
| `young_female.pth` | Younger female dialogue | female |
| `young_male.pth` | Younger male dialogue | male |
| `older_narrator.pth` | Older narrator | male |

Optional sidecar `narrator.json`:

```json
{
  "role": "narrator",
  "gender": "male",
  "description": "Steady fiction narrator",
  "index": "narrator.index"
}
```

## Download

```bash
# From repo root — creates RVC 3.12 venv, hubert/rmvpe, Piper voices
make setup-voices

# Also try Hugging Face starter .pth downloads (see voices.manifest.json)
make setup-voices DOWNLOAD_STARTERS=1
```

If a starter download fails (license / path changes), place your own `.pth` files using the names above. Train or clone a custom character (e.g. Raksa) in the [RVC WebUI](https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI) and copy the resulting `.pth` (+ `.index`) into this folder.

## Required assets (not in this folder)

HuBERT + RMVPE live in the RVC checkout (`LOKALREADER_RVC_ROOT` or `.rvc/…`):

- `assets/hubert_base/pytorch_model.bin`
- `assets/rmvpe/rmvpe.pt`

From [lj1995/VoiceConversionWebUI](https://huggingface.co/lj1995/VoiceConversionWebUI).
