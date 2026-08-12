#!/usr/bin/env python3
"""Download recommended starter RVC .pth models from Hugging Face.

Reads data/rvc_weights/voices.manifest.json. Does not vendor models in git.
Failures are non-fatal per model so users can place files manually.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--weights-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "data" / "rvc_weights",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).resolve().parents[1]
        / "data"
        / "rvc_weights"
        / "voices.manifest.json",
    )
    args = parser.parse_args()

    try:
        from huggingface_hub import hf_hub_download, list_repo_files
    except ImportError:
        print("huggingface_hub required", file=sys.stderr)
        return 1

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    args.weights_dir.mkdir(parents=True, exist_ok=True)
    ok = 0
    failed = 0

    for entry in manifest.get("models", []):
        dest_name = entry.get("rename_to") or f"{entry['id']}.pth"
        dest = args.weights_dir / dest_name
        sidecar = dest.with_suffix(".json")
        sidecar.write_text(
            json.dumps(
                {
                    "role": entry.get("role"),
                    "gender": entry.get("gender"),
                    "description": entry.get("description", ""),
                    "hf_repo": entry.get("hf_repo"),
                    "license_note": entry.get("license_note", ""),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if dest.exists() and dest.stat().st_size > 1000:
            print(f"[skip] {dest.name} already present")
            ok += 1
            continue

        repo = entry["hf_repo"]
        files = entry.get("hf_files") or []
        print(f"[fetch] {entry['id']} from {repo} …")
        downloaded = None
        for filename in files:
            try:
                path = hf_hub_download(repo_id=repo, filename=filename)
                downloaded = Path(path)
                break
            except Exception as exc:
                print(f"  miss {filename}: {exc}")

        if downloaded is None:
            # Try first .pth in repo
            try:
                repo_files = list_repo_files(repo)
                pths = [f for f in repo_files if f.lower().endswith(".pth")]
                if pths:
                    path = hf_hub_download(repo_id=repo, filename=pths[0])
                    downloaded = Path(path)
                    print(f"  fell back to {pths[0]}")
            except Exception as exc:
                print(f"  repo list failed: {exc}")

        if downloaded is None:
            print(f"[FAIL] {entry['id']} — place {dest_name} manually")
            failed += 1
            continue

        shutil.copy2(downloaded, dest)
        print(f"[ok] {dest}")
        ok += 1

        # Best-effort index
        try:
            repo_files = list_repo_files(repo)
            indexes = [f for f in repo_files if f.lower().endswith(".index")]
            if indexes:
                idx_path = Path(hf_hub_download(repo_id=repo, filename=indexes[0]))
                idx_dest = args.weights_dir / f"{Path(dest_name).stem}.index"
                shutil.copy2(idx_path, idx_dest)
                print(f"[ok] index {idx_dest.name}")
        except Exception as exc:
            print(f"  index skip: {exc}")

    print(f"Done: {ok} ok, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
