#!/usr/bin/env python3
"""Example RVC infer CLI contract for LokalReader.

Point LOKALREADER_RVC_INFER_SCRIPT at a real script from your
Retrieval-based-Voice-Conversion-WebUI install (or wrap its infer API
to match these flags).

Usage:
  python rvc_infer_stub.py --model /path/to/voice.pth --input in.wav --output out.wav

This stub copies the input wav to the output and exits 0, so you can
verify wiring without a GPU / RVC environment.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="LokalReader RVC infer contract (stub)")
    parser.add_argument("--model", required=True, help="Path to .pth model")
    parser.add_argument("--input", required=True, help="Input WAV from LocalTTS")
    parser.add_argument("--output", required=True, help="Converted WAV output path")
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
    print(f"[rvc-stub] copied {src} -> {dst} using model {model.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
