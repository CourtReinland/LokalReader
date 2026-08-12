"""Application paths and optional RVC configuration."""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("LOKALREADER_DATA", ROOT / "data"))
BOOKS_DIR = DATA_DIR / "books"
AUDIO_DIR = DATA_DIR / "audio"
MAPPINGS_DIR = DATA_DIR / "mappings"
FRONTEND_DIR = ROOT / "frontend"

# Optional RVC install (Retrieval-based-Voice-Conversion-WebUI)
RVC_ROOT = Path(os.environ.get("LOKALREADER_RVC_ROOT", "")).expanduser() if os.environ.get("LOKALREADER_RVC_ROOT") else None
RVC_WEIGHTS = Path(
    os.environ.get(
        "LOKALREADER_RVC_WEIGHTS",
        str(RVC_ROOT / "assets" / "weights") if RVC_ROOT else DATA_DIR / "rvc_weights",
    )
).expanduser()
RVC_PYTHON = os.environ.get("LOKALREADER_RVC_PYTHON", "python3")
RVC_INFER_SCRIPT = Path(os.environ.get("LOKALREADER_RVC_INFER_SCRIPT", "")) if os.environ.get("LOKALREADER_RVC_INFER_SCRIPT") else None

DEFAULT_RATE = 1.0


def ensure_dirs() -> None:
    for path in (DATA_DIR, BOOKS_DIR, AUDIO_DIR, MAPPINGS_DIR, RVC_WEIGHTS):
        path.mkdir(parents=True, exist_ok=True)
