#!/usr/bin/env python3
"""LokalReader → RVC WebUI inference bridge.

Runs inside (or via) the Python 3.12 RVC venv. Invokes the official
Retrieval-based-Voice-Conversion-WebUI CLI as a module:

  python -m infer.cli --model … --input … --output … --f0-method rmvpe

Invoking `python infer/cli.py` is NOT enough: `infer.cli` does
`from infer.vc…`, which requires RVC_ROOT on sys.path. We therefore:
  1) run with cwd=RVC_ROOT
  2) prepend RVC_ROOT to PYTHONPATH
  3) invoke via `python -m infer.cli`

Contract (stable for LokalReader):
  python rvc_infer.py --model /path/to/voice.pth --input in.wav --output out.wav
                       [--index /path/to.added.index]

Environment:
  LOKALREADER_RVC_ROOT / RVC_ROOT — checkout of RVC-Project/Retrieval-based-Voice-Conversion-WebUI
  LOKALREADER_RVC_USE_INDEX=1 — opt into FAISS .index retrieval (off by default; faiss-cpu
    SIGSEGV on Apple Silicon with --index / --index-rate > 0)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def _resolve_root() -> Path:
    for key in ("LOKALREADER_RVC_ROOT", "RVC_ROOT"):
        raw = os.environ.get(key, "").strip()
        if raw:
            return Path(raw).expanduser().resolve()
    # Default: sibling checkout managed by setup_voices.sh
    here = Path(__file__).resolve().parent.parent
    return (here / ".rvc" / "Retrieval-based-Voice-Conversion-WebUI").resolve()


def _env_with_rvc_path(base: dict[str, str], root: Path) -> dict[str, str]:
    """Ensure RVC_ROOT is first on PYTHONPATH so `import infer` works."""
    env = dict(base)
    root_s = str(root)
    existing = env.get("PYTHONPATH", "").strip()
    parts = [p for p in existing.split(os.pathsep) if p]
    if root_s not in parts:
        parts.insert(0, root_s)
    elif parts[0] != root_s:
        parts = [root_s] + [p for p in parts if p != root_s]
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env


def _use_faiss_index() -> bool:
    """FAISS index retrieval is opt-in — faiss-cpu can SIGSEGV on Apple Silicon."""
    return os.environ.get("LOKALREADER_RVC_USE_INDEX", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def resolve_index_args(
    *,
    index: str,
    index_rate: float,
    use_index: bool | None = None,
) -> list[str]:
    """Build --index / --index-rate flags.

    Default: --index-rate 0 (no FAISS). With LOKALREADER_RVC_USE_INDEX=1 and a
    present index file, pass --index and the requested rate.
    """
    if use_index is None:
        use_index = _use_faiss_index()
    if not use_index:
        return ["--index-rate", "0"]
    index_path = Path(index).expanduser() if index else None
    if index_path and index_path.is_file():
        rate = max(0.0, min(1.0, float(index_rate)))
        return ["--index", str(index_path.resolve()), "--index-rate", str(rate)]
    # Opt-in but no index file — still disable retrieval
    return ["--index-rate", "0"]


def build_rvc_cmd(
    *,
    python: str,
    model: Path,
    src: Path,
    dst: Path,
    f0_method: str,
    pitch: int,
    index_args: list[str],
) -> list[str]:
    return [
        python,
        "-m",
        "infer.cli",
        "--model",
        str(model),
        "--input",
        str(src),
        "--output",
        str(dst),
        "--f0-method",
        f0_method,
        "--pitch",
        str(pitch),
        "--overwrite",
        "--format",
        "wav",
        *index_args,
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="LokalReader RVC infer bridge")
    parser.add_argument("--model", required=True, help="Path to .pth model")
    parser.add_argument("--input", required=True, help="Input WAV from Piper TTS")
    parser.add_argument("--output", required=True, help="Converted WAV output path")
    parser.add_argument("--index", default="", help="Optional FAISS .index path")
    parser.add_argument("--pitch", type=int, default=0)
    parser.add_argument(
        "--index-rate",
        type=float,
        default=0.75,
        help="Used only when LOKALREADER_RVC_USE_INDEX=1 (default path forces 0)",
    )
    parser.add_argument("--f0-method", default="rmvpe", choices=["rmvpe", "pm"])
    args = parser.parse_args()

    model = Path(args.model).expanduser().resolve()
    src = Path(args.input).expanduser().resolve()
    dst = Path(args.output).expanduser().resolve()
    if not model.is_file():
        print(f"rvc_infer: model missing: {model}", file=sys.stderr)
        return 2
    if not src.is_file():
        print(f"rvc_infer: input missing: {src}", file=sys.stderr)
        return 2

    root = _resolve_root()
    cli = root / "infer" / "cli.py"
    if not cli.is_file():
        print(
            f"rvc_infer: RVC CLI not found at {cli}. "
            "Clone RVC-Project/Retrieval-based-Voice-Conversion-WebUI and set "
            "LOKALREADER_RVC_ROOT, or run `make setup-voices`.",
            file=sys.stderr,
        )
        return 2

    dst.parent.mkdir(parents=True, exist_ok=True)

    # Point weight_root at the model directory so relative names resolve
    env = _env_with_rvc_path(os.environ.copy(), root)
    env["weight_root"] = str(model.parent)
    env.setdefault("rmvpe_root", str(root / "assets" / "rmvpe"))
    env.setdefault("index_root", str(root / "logs"))
    env.setdefault("outside_index_root", str(root / "assets" / "indices"))

    index_args = resolve_index_args(index=args.index, index_rate=args.index_rate)
    if index_args == ["--index-rate", "0"] and args.index:
        print(
            "[rvc_infer] FAISS index disabled (default). "
            "Set LOKALREADER_RVC_USE_INDEX=1 to enable — "
            "faiss-cpu may SIGSEGV on Apple Silicon.",
            flush=True,
        )

    cmd = build_rvc_cmd(
        python=sys.executable,
        model=model,
        src=src,
        dst=dst,
        f0_method=args.f0_method,
        pitch=args.pitch,
        index_args=index_args,
    )
    print(
        f"[rvc_infer] cwd={root} PYTHONPATH={env.get('PYTHONPATH')} cmd={' '.join(cmd)}",
        flush=True,
    )
    proc = subprocess.run(cmd, cwd=str(root), env=env)
    if proc.returncode != 0:
        if proc.returncode == -11 or proc.returncode == 139:
            print(
                "rvc_infer: RVC process crashed (SIGSEGV / exit 139). "
                "On Apple Silicon this is often faiss-cpu index retrieval — "
                "ensure LOKALREADER_RVC_USE_INDEX is unset (default --index-rate 0).",
                file=sys.stderr,
            )
        return proc.returncode
    if not dst.is_file() or dst.stat().st_size < 44:
        print(f"rvc_infer: output missing or empty: {dst}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
