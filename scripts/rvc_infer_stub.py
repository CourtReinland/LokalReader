#!/usr/bin/env python3
"""Wiring-only RVC stub for CI / pipeline tests.

Copies the Piper TTS wav through unchanged. NOT a real timbre conversion.
Production uses scripts/rvc_infer.py against a Python 3.12 RVC WebUI checkout.

Usage:
  python rvc_infer_stub.py --model /path/to/voice.pth --input in.wav --output out.wav
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="LokalReader RVC infer stub (passthrough)")
    parser.add_argument("--model", required=True, help="Path to .pth model")
    parser.add_argument("--input", required=True, help="Input WAV from Piper TTS")
    parser.add_argument("--output", required=True, help="Converted WAV output path")
    parser.add_argument("--index", default="", help="Ignored in stub")
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)
    model = Path(args.model)
    if not src.exists():
        raise SystemExit(f"input missing: {src}")
    if not model.exists():
        raise SystemExit(f"model missing: {model}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    print(f"[rvc-stub] PASSTHROUGH {src} -> {dst} (model {model.name}; not real RVC)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
