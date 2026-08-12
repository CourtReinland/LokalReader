"""Application paths and RVC / Piper configuration."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("LOKALREADER_DATA", ROOT / "data")).expanduser()
BOOKS_DIR = DATA_DIR / "books"
AUDIO_DIR = DATA_DIR / "audio"
MAPPINGS_DIR = DATA_DIR / "mappings"
FRONTEND_DIR = ROOT / "frontend"

# Piper neural TTS (base synthesizer — never macOS say / espeak for user voices)
PIPER_VOICES_DIR = Path(
    os.environ.get("LOKALREADER_PIPER_VOICES", DATA_DIR / "piper_voices")
).expanduser()
PIPER_DEFAULT_VOICE = os.environ.get("LOKALREADER_PIPER_VOICE", "en_US-lessac-medium")
PIPER_FEMALE_VOICE = os.environ.get("LOKALREADER_PIPER_VOICE_FEMALE", "en_US-amy-medium")
PIPER_MALE_VOICE = os.environ.get("LOKALREADER_PIPER_VOICE_MALE", "en_US-lessac-medium")

# RVC install (Retrieval-based-Voice-Conversion-WebUI) — Python 3.12 subprocess
_RVC_ROOT_ENV = os.environ.get("LOKALREADER_RVC_ROOT", "").strip()
RVC_ROOT = Path(_RVC_ROOT_ENV).expanduser() if _RVC_ROOT_ENV else (ROOT / ".rvc" / "Retrieval-based-Voice-Conversion-WebUI")
RVC_WEIGHTS = Path(
    os.environ.get("LOKALREADER_RVC_WEIGHTS", DATA_DIR / "rvc_weights")
).expanduser()
RVC_VENV = Path(os.environ.get("LOKALREADER_RVC_VENV", ROOT / ".venv-rvc")).expanduser()
_RVC_PYTHON_ENV = os.environ.get("LOKALREADER_RVC_PYTHON", "").strip()
if _RVC_PYTHON_ENV:
    RVC_PYTHON = _RVC_PYTHON_ENV
elif (RVC_VENV / "bin" / "python").exists():
    RVC_PYTHON = str(RVC_VENV / "bin" / "python")
elif (RVC_VENV / "Scripts" / "python.exe").exists():
    RVC_PYTHON = str(RVC_VENV / "Scripts" / "python.exe")
else:
    RVC_PYTHON = "python3.12"

_DEFAULT_INFER = ROOT / "scripts" / "rvc_infer.py"
_RVC_INFER_ENV = os.environ.get("LOKALREADER_RVC_INFER_SCRIPT", "").strip()
RVC_INFER_SCRIPT = Path(_RVC_INFER_ENV).expanduser() if _RVC_INFER_ENV else _DEFAULT_INFER

# Disabled by default. When "1", expose piper:* voices and allow synthesis without RVC
# (labeled emergency / CI path — never silent macOS say fallback).
ALLOW_EMERGENCY_TTS = os.environ.get("LOKALREADER_ALLOW_EMERGENCY_TTS", "").strip() in {
    "1",
    "true",
    "yes",
}

DEFAULT_RATE = 1.0


def ensure_dirs() -> None:
    for path in (DATA_DIR, BOOKS_DIR, AUDIO_DIR, MAPPINGS_DIR, RVC_WEIGHTS, PIPER_VOICES_DIR):
        path.mkdir(parents=True, exist_ok=True)
