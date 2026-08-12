"""RVC post-pass: Piper WAV → character timbre via local .pth models.

RVC is a voice conversion / timbre changer, NOT a TTS engine.
Pipeline: text → Piper neural TTS → RVC (Python 3.12 subprocess) → playback.

Never falls back silently to macOS `say` / Samantha / espeak.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
from pathlib import Path

from lokalreader import config
from lokalreader.models import VoiceInfo
from lokalreader.voices.base import VoiceBackend
from lokalreader.voices.errors import VoiceSetupError
from lokalreader.voices.piper_tts import PiperTTSBackend

logger = logging.getLogger(__name__)

ROLE_LABELS = {
    "narrator": "Narrator",
    "young_female": "Young female",
    "young_male": "Young male",
    "older_narrator": "Older narrator",
}


class RVCVoiceBackend(VoiceBackend):
    name = "rvc"

    def __init__(self, base: PiperTTSBackend | None = None) -> None:
        self.base = base or PiperTTSBackend()

    def available(self) -> bool:
        status = rvc_status()
        return bool(status.get("available")) and self.base.available()

    def list_voices(self) -> list[VoiceInfo]:
        voices: list[VoiceInfo] = []
        for meta in iter_weight_metas():
            stem = meta["stem"]
            role = meta.get("role") or ""
            label = ROLE_LABELS.get(role, stem.replace("_", " ").title())
            voices.append(
                VoiceInfo(
                    id=f"rvc:{stem}",
                    name=f"RVC · {label}",
                    engine="rvc",
                    gender=meta.get("gender"),
                    description=meta.get("description")
                    or f"RVC timbre model ({meta['pth'].name})",
                    rvc_model=stem,
                )
            )
        return voices

    def synthesize(self, text: str, voice_id: str, out_path: Path, *, speed: float = 1.0) -> Path:
        if not voice_id.startswith("rvc:"):
            if voice_id.startswith("piper:") and config.ALLOW_EMERGENCY_TTS:
                return self.base.synthesize(text, voice_id, out_path, speed=speed)
            raise VoiceSetupError(
                f"Unsupported voice id '{voice_id}'. Assign an rvc:<model> voice "
                "(macOS system voices and espeak are not available).",
                missing=["rvc:* voice mapping"],
            )

        model = voice_id.split(":", 1)[1]
        meta = weight_meta_for(model)
        if meta is None:
            raise VoiceSetupError(
                f"RVC model '{model}' not found.",
                missing=[f"{model}.pth in {config.RVC_WEIGHTS}"],
            )

        status = rvc_status()
        if not status["available"]:
            raise VoiceSetupError(
                "RVC conversion subprocess is not ready.",
                missing=status.get("missing") or ["RVC setup"],
            )

        gender = meta.get("gender")
        base_id = self.base.base_voice_for_gender(gender)

        import tempfile

        with tempfile.TemporaryDirectory(prefix="lokalreader-tts-") as tmp:
            src = Path(tmp) / "tts.wav"
            self.base.synthesize(text, base_id, src, speed=speed)
            self._run_rvc(src, meta, out_path)
        return out_path

    def _run_rvc(self, wav_in: Path, meta: dict, wav_out: Path) -> None:
        script = config.RVC_INFER_SCRIPT
        if script is None or not Path(script).exists():
            raise VoiceSetupError(
                "RVC infer script missing.",
                missing=[str(config.RVC_INFER_SCRIPT)],
            )
        model_path: Path = meta["pth"]
        index_path: Path | None = meta.get("index")
        wav_out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            config.RVC_PYTHON,
            str(script),
            "--model",
            str(model_path),
            "--input",
            str(wav_in),
            "--output",
            str(wav_out),
        ]
        if index_path and index_path.exists():
            cmd.extend(["--index", str(index_path)])
        env = os.environ.copy()
        env["RVC_ROOT"] = str(config.RVC_ROOT)
        env["LOKALREADER_RVC_ROOT"] = str(config.RVC_ROOT)
        env["LOKALREADER_RVC_WEIGHTS"] = str(config.RVC_WEIGHTS)
        try:
            proc = subprocess.run(
                cmd,
                check=False,
                capture_output=True,
                env=env,
                timeout=180,
                text=True,
            )
        except FileNotFoundError as exc:
            raise VoiceSetupError(
                f"RVC Python not found: {config.RVC_PYTHON}",
                missing=["Python 3.12 RVC venv (make setup-voices)"],
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise VoiceSetupError("RVC inference timed out.") from exc

        if proc.returncode != 0 or not wav_out.exists() or wav_out.stat().st_size < 44:
            detail = (proc.stderr or proc.stdout or "").strip()[-800:]
            raise VoiceSetupError(
                "RVC conversion failed.",
                missing=[detail or f"exit code {proc.returncode}"],
            )


def iter_weight_metas() -> list[dict]:
    root = config.RVC_WEIGHTS
    if not root.exists():
        return []
    metas: list[dict] = []
    for pth in sorted(root.glob("*.pth")):
        metas.append(_meta_for_pth(pth))
    return metas


def weight_meta_for(stem: str) -> dict | None:
    for meta in iter_weight_metas():
        if meta["stem"] == stem or meta["pth"].stem == stem:
            return meta
        # allow prefix match (legacy)
        if meta["stem"].startswith(stem):
            return meta
    matches = list(config.RVC_WEIGHTS.glob(f"{stem}*.pth")) if config.RVC_WEIGHTS.exists() else []
    if matches:
        return _meta_for_pth(matches[0])
    return None


def _meta_for_pth(pth: Path) -> dict:
    stem = pth.stem
    meta = {
        "stem": stem,
        "pth": pth,
        "index": _find_index(stem),
        "role": None,
        "gender": None,
        "description": "",
    }
    sidecar = pth.with_suffix(".json")
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            meta["role"] = data.get("role")
            meta["gender"] = data.get("gender")
            meta["description"] = data.get("description") or ""
            if data.get("index"):
                idx = Path(data["index"])
                if not idx.is_absolute():
                    idx = config.RVC_WEIGHTS / idx
                if idx.exists():
                    meta["index"] = idx
        except Exception as exc:
            logger.debug("Bad sidecar %s: %s", sidecar, exc)
    # Infer role/gender from stem conventions
    lower = stem.lower()
    if not meta["role"]:
        for role in ROLE_LABELS:
            if role in lower or role.replace("_", "-") in lower:
                meta["role"] = role
                break
    if not meta["gender"]:
        if any(x in lower for x in ("female", "woman", "girl", "amy", "mara")):
            meta["gender"] = "female"
        elif any(x in lower for x in ("male", "man", "boy", "eli", "joe", "alan")):
            meta["gender"] = "male"
    return meta


def _find_index(stem: str) -> Path | None:
    root = config.RVC_WEIGHTS
    candidates = [
        root / f"{stem}.index",
        root / f"{stem}.added.index",
        *root.glob(f"*{stem}*.index"),
        *root.glob(f"added_*{stem}*.index"),
    ]
    for c in candidates:
        if c.is_file():
            return c
    return None


def rvc_status() -> dict:
    weights = iter_weight_metas()
    weight_names = [m["pth"].name for m in weights]
    script = config.RVC_INFER_SCRIPT
    script_ok = bool(script and Path(script).exists())
    rvc_root = config.RVC_ROOT
    rvc_cli = rvc_root / "infer" / "cli.py" if rvc_root else None
    hubert = (
        (rvc_root / "assets" / "hubert_base" / "pytorch_model.bin")
        if rvc_root
        else None
    )
    rmvpe = (rvc_root / "assets" / "rmvpe" / "rmvpe.pt") if rvc_root else None

    python_ok = _python_seems_ok(config.RVC_PYTHON)
    # Stub scripts (wiring/tests) do not need hubert/rmvpe/RVC checkout
    is_stub = script_ok and "stub" in Path(script).name.lower()
    assets_ok = is_stub or (
        bool(rvc_cli and rvc_cli.exists())
        and bool(hubert and hubert.exists())
        and bool(rmvpe and rmvpe.exists())
    )

    missing: list[str] = []
    if not weight_names:
        missing.append(f"RVC .pth models in {config.RVC_WEIGHTS} (see data/rvc_weights/README.md)")
    if not script_ok:
        missing.append(f"infer script at {script}")
    if not python_ok:
        missing.append(f"RVC Python 3.12 at {config.RVC_PYTHON} (.venv-rvc via make setup-voices)")
    if not is_stub:
        if not rvc_root or not rvc_root.exists():
            missing.append(
                f"RVC WebUI checkout at {rvc_root} (set LOKALREADER_RVC_ROOT or make setup-voices)"
            )
        else:
            if not (rvc_cli and rvc_cli.exists()):
                missing.append(f"RVC infer CLI ({rvc_cli})")
            if not (hubert and hubert.exists()):
                missing.append("hubert assets (hf download lj1995/VoiceConversionWebUI hubert_base/*)")
            if not (rmvpe and rmvpe.exists()):
                missing.append("rmvpe.pt (hf download lj1995/VoiceConversionWebUI rmvpe.pt)")

    ready = bool(weight_names) and script_ok and python_ok and assets_ok
    state = "ready" if ready else ("missing_models" if not weight_names else "setup_incomplete")

    return {
        "state": state,
        "available": ready,
        "configured_root": str(rvc_root) if rvc_root else None,
        "weights_dir": str(config.RVC_WEIGHTS),
        "weights": weight_names,
        "infer_script": str(script) if script else None,
        "python": config.RVC_PYTHON,
        "python_ok": python_ok,
        "hubert_ok": bool(hubert and hubert.exists()) if not is_stub else True,
        "rmvpe_ok": bool(rmvpe and rmvpe.exists()) if not is_stub else True,
        "missing": missing,
        "setup_hint": None if ready else "Run `make setup-voices` (Python 3.12 RVC venv + hubert/rmvpe + .pth models).",
        "note": (
            "RVC converts Piper TTS audio timbre; it does not synthesize speech from text. "
            "macOS system voices (say) are not used."
        ),
    }


def _python_seems_ok(python_cmd: str) -> bool:
    path = Path(python_cmd)
    if path.is_file():
        return True
    # bare command — check PATH
    import shutil

    return shutil.which(python_cmd) is not None
