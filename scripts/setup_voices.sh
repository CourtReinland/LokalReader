#!/usr/bin/env bash
# LokalReader voice setup: Piper neural TTS + RVC (Python 3.12) + hubert/rmvpe.
# Usage:
#   ./scripts/setup_voices.sh
#   DOWNLOAD_STARTERS=1 ./scripts/setup_voices.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

PYTHON312="${PYTHON312:-}"
if [[ -z "$PYTHON312" ]]; then
  if command -v python3.12 >/dev/null 2>&1; then
    PYTHON312="$(command -v python3.12)"
  elif command -v python3 >/dev/null 2>&1 && [[ "$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')" == "3.12" ]]; then
    PYTHON312="$(command -v python3)"
  else
    echo "ERROR: Python 3.12 is required for the RVC subprocess."
    echo "  macOS:  brew install python@3.12"
    echo "  Ubuntu: sudo apt install python3.12 python3.12-venv"
    exit 1
  fi
fi

APP_VENV="${VENV:-$ROOT/.venv}"
RVC_VENV="${LOKALREADER_RVC_VENV:-$ROOT/.venv-rvc}"
RVC_ROOT="${LOKALREADER_RVC_ROOT:-$ROOT/.rvc/Retrieval-based-Voice-Conversion-WebUI}"
PIPER_DIR="${LOKALREADER_PIPER_VOICES:-$ROOT/data/piper_voices}"
WEIGHTS_DIR="${LOKALREADER_RVC_WEIGHTS:-$ROOT/data/rvc_weights}"
DOWNLOAD_STARTERS="${DOWNLOAD_STARTERS:-0}"
RVC_REPO_URL="${RVC_REPO_URL:-https://github.com/RVC-Project/Retrieval-based-Voice-Conversion-WebUI.git}"

echo "==> LokalReader voice setup"
echo "    app venv:   $APP_VENV"
echo "    rvc venv:   $RVC_VENV  ($PYTHON312)"
echo "    rvc root:   $RVC_ROOT"
echo "    piper dir:  $PIPER_DIR"
echo "    weights:    $WEIGHTS_DIR"

mkdir -p "$PIPER_DIR" "$WEIGHTS_DIR" "$(dirname "$RVC_ROOT")"

# --- App venv + Piper ---
if [[ ! -x "$APP_VENV/bin/python" ]]; then
  echo "==> Creating app venv"
  python3 -m venv "$APP_VENV"
fi
# shellcheck disable=SC1091
source "$APP_VENV/bin/activate"
pip install -q -U pip
pip install -q -r "$ROOT/requirements.txt"
echo "==> Downloading Piper voices"
python -m piper.download_voices en_US-lessac-medium --download-dir "$PIPER_DIR" || true
python -m piper.download_voices en_US-amy-medium --download-dir "$PIPER_DIR" || true
# Flatten nested downloads if present
shopt -s nullglob
for d in "$PIPER_DIR"/*/; do
  for f in "$d"*.onnx "$d"*.onnx.json; do
    [[ -f "$f" ]] || continue
    base="$(basename "$f")"
    if [[ ! -f "$PIPER_DIR/$base" ]]; then
      cp -f "$f" "$PIPER_DIR/$base"
    fi
  done
done
shopt -u nullglob

# --- RVC WebUI checkout ---
if [[ ! -d "$RVC_ROOT/.git" ]]; then
  echo "==> Cloning RVC WebUI → $RVC_ROOT"
  git clone --depth 1 "$RVC_REPO_URL" "$RVC_ROOT"
else
  echo "==> RVC WebUI already present"
fi

# --- RVC 3.12 venv ---
if [[ ! -x "$RVC_VENV/bin/python" && ! -x "$RVC_VENV/Scripts/python.exe" ]]; then
  echo "==> Creating RVC Python 3.12 venv"
  "$PYTHON312" -m venv "$RVC_VENV"
fi
if [[ -x "$RVC_VENV/bin/python" ]]; then
  RVC_PY="$RVC_VENV/bin/python"
  RVC_PIP="$RVC_VENV/bin/pip"
else
  RVC_PY="$RVC_VENV/Scripts/python.exe"
  RVC_PIP="$RVC_VENV/Scripts/pip.exe"
fi
"$RVC_PIP" install -q -U pip setuptools wheel
"$RVC_PIP" install -q huggingface_hub

OS="$(uname -s)"
REQ_SRC="$RVC_ROOT/requirments_cpu_py312.txt"
REQ_LOCAL="$ROOT/.rvc/requirements_cpu_local.txt"
mkdir -p "$ROOT/.rvc"
if [[ -f "$REQ_SRC" ]]; then
  # Prefer official indexes (PKU/NJU mirrors can be slow outside CN)
  sed -E \
    -e 's|--index-url https://mirrors.pku.edu.cn/pypi/simple|--index-url https://pypi.org/simple|' \
    -e 's|--extra-index-url https://mirrors.nju.edu.cn/pytorch/whl/cpu|--extra-index-url https://download.pytorch.org/whl/cpu|' \
    "$REQ_SRC" > "$REQ_LOCAL"
else
  echo "WARNING: $REQ_SRC missing — installing minimal torch + deps"
  echo "torch" > "$REQ_LOCAL"
fi

echo "==> Installing RVC CPU/MPS-friendly dependencies (this can take a while)"
if [[ "$OS" == "Darwin" ]]; then
  # Apple Silicon / macOS: stock torch wheels (MPS/CPU), not Linux +cpu builds
  "$RVC_PIP" install -q "torch" "torchaudio" "torchvision"
  # Filter out torch pin lines and Windows-only packages for the rest
  grep -vE '^(torch|torchaudio|torchvision|torch-directml|--index-url|--extra-index-url)' "$REQ_LOCAL" \
    | grep -v 'platform_system' \
    > "$ROOT/.rvc/requirements_mac_rest.txt" || true
  "$RVC_PIP" install -q -r "$ROOT/.rvc/requirements_mac_rest.txt" || {
    echo "WARNING: full RVC requirements install had errors; installing core infer deps"
    "$RVC_PIP" install -q numpy scipy librosa soundfile faiss-cpu praat-parselmouth \
      transformers==4.49.0 ffmpeg-python av tqdm pyyaml scikit-learn onnxruntime
  }
else
  "$RVC_PIP" install -q -r "$REQ_LOCAL" || {
    echo "WARNING: requirments_cpu_py312.txt failed; trying official torch CPU + core deps"
    "$RVC_PIP" install -q torch torchaudio --index-url https://download.pytorch.org/whl/cpu
    "$RVC_PIP" install -q numpy scipy librosa soundfile faiss-cpu praat-parselmouth \
      transformers==4.49.0 ffmpeg-python av tqdm pyyaml scikit-learn onnxruntime
  }
fi

# --- HuBERT + RMVPE ---
echo "==> Downloading HuBERT + RMVPE from lj1995/VoiceConversionWebUI"
"$RVC_PY" - <<PY
from pathlib import Path
from huggingface_hub import hf_hub_download, snapshot_download

root = Path(r"""$RVC_ROOT""")
assets = root / "assets"
assets.mkdir(parents=True, exist_ok=True)
# hubert_base/*
snapshot_download(
    repo_id="lj1995/VoiceConversionWebUI",
    allow_patterns=["hubert_base/*"],
    local_dir=str(assets),
)
rmvpe_dir = assets / "rmvpe"
rmvpe_dir.mkdir(parents=True, exist_ok=True)
path = hf_hub_download(
    repo_id="lj1995/VoiceConversionWebUI",
    filename="rmvpe.pt",
    local_dir=str(rmvpe_dir),
)
print("rmvpe:", path)
hubert = assets / "hubert_base" / "pytorch_model.bin"
print("hubert ok:", hubert.exists(), hubert)
PY

# --- Optional starter .pth models ---
if [[ "$DOWNLOAD_STARTERS" == "1" ]]; then
  echo "==> Downloading starter RVC models from voices.manifest.json"
  "$RVC_PY" "$ROOT/scripts/download_starter_voices.py" --weights-dir "$WEIGHTS_DIR" || {
    echo "WARNING: some starter downloads failed — place .pth files manually (see data/rvc_weights/README.md)"
  }
else
  echo "==> Skipping starter .pth downloads (set DOWNLOAD_STARTERS=1 to fetch recommended models)"
  echo "    Place narrator.pth / young_female.pth / young_male.pth / older_narrator.pth in:"
  echo "    $WEIGHTS_DIR"
fi

# Write env hint file
cat > "$ROOT/.rvc/env.sh" <<EOF
# Source this or export before make run
export LOKALREADER_RVC_ROOT="$RVC_ROOT"
export LOKALREADER_RVC_VENV="$RVC_VENV"
export LOKALREADER_RVC_PYTHON="$RVC_PY"
export LOKALREADER_RVC_WEIGHTS="$WEIGHTS_DIR"
export LOKALREADER_PIPER_VOICES="$PIPER_DIR"
export LOKALREADER_RVC_INFER_SCRIPT="$ROOT/scripts/rvc_infer.py"
EOF

echo ""
echo "Setup complete."
echo "  Piper voices:  $PIPER_DIR"
echo "  RVC checkout:  $RVC_ROOT"
echo "  RVC python:    $RVC_PY"
echo "  Weights:       $WEIGHTS_DIR"
echo ""
echo "Next:"
echo "  source .rvc/env.sh   # optional — make run auto-loads if present"
echo "  make run"
echo ""
if [[ -z "$(ls -A "$WEIGHTS_DIR"/*.pth 2>/dev/null || true)" ]]; then
  echo "NOTE: No .pth models yet. Run with DOWNLOAD_STARTERS=1 or copy models into data/rvc_weights/."
  echo "      Until then, /api/voices will report missing models (no Samantha fallback)."
fi
