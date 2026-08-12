"""Optional RVC post-pass: TTS wav → character timbre via local .pth models.

RVC (Retrieval-based-Voice-Conversion) is a voice conversion / timbre changer,
NOT a text-to-speech engine. This backend always synthesizes with LocalTTS first,
then optionally converts the waveform if RVC is configured and models are present.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from lokalreader import config
from lokalreader.models import VoiceInfo
from lokalreader.voices.base import VoiceBackend
from lokalreader.voices.local_tts import LocalTTSBackend

logger = logging.getLogger(__name__)


class RVCVoiceBackend(VoiceBackend):
    name = "rvc"

    def __init__(self, base: LocalTTSBackend | None = None) -> None:
        self.base = base or LocalTTSBackend()

    def available(self) -> bool:
        return bool(self._weights()) and self.base.available()

    def _weights(self) -> list[Path]:
        root = config.RVC_WEIGHTS
        if not root.exists():
            return []
        return sorted(root.glob("*.pth"))

    def list_voices(self) -> list[VoiceInfo]:
        voices = self.base.list_voices()
        for pth in self._weights():
            voices.append(
                VoiceInfo(
                    id=f"rvc:{pth.stem}",
                    name=f"RVC · {pth.stem}",
                    engine="rvc",
                    description=f"Local RVC model ({pth.name}) — converts TTS audio timbre",
                    rvc_model=pth.stem,
                )
            )
        return voices

    def synthesize(self, text: str, voice_id: str, out_path: Path, *, speed: float = 1.0) -> Path:
        if not voice_id.startswith("rvc:"):
            return self.base.synthesize(text, voice_id, out_path, speed=speed)

        model = voice_id.split(":", 1)[1]
        # Pick a stable base TTS voice for the conversion source
        base_voices = self.base.list_voices()
        base_id = base_voices[0].id if base_voices else "espeak:en+m3"

        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "tts.wav"
            self.base.synthesize(text, base_id, src, speed=speed)
            if not self._run_rvc(src, model, out_path):
                logger.warning("RVC conversion unavailable for %s — falling back to LocalTTS", model)
                return self.base.synthesize(text, base_id, out_path, speed=speed)
        return out_path

    def _run_rvc(self, wav_in: Path, model_name: str, wav_out: Path) -> bool:
        """Invoke a user-provided RVC infer script if configured.

        Expected environment:
          LOKALREADER_RVC_ROOT   — clone of Retrieval-based-Voice-Conversion-WebUI
          LOKALREADER_RVC_WEIGHTS — directory with *.pth (default: $RVC_ROOT/assets/weights)
          LOKALREADER_RVC_INFER_SCRIPT — python script that accepts:
                --model NAME --input WAV --output WAV
          LOKALREADER_RVC_PYTHON — python used to run the script
        """
        weights = config.RVC_WEIGHTS
        model_path = weights / f"{model_name}.pth"
        if not model_path.exists():
            # allow bare stem match
            matches = list(weights.glob(f"{model_name}*.pth"))
            if not matches:
                return False
            model_path = matches[0]

        script = config.RVC_INFER_SCRIPT
        if script is None or not Path(script).exists():
            # Try conventional helper inside RVC root
            if config.RVC_ROOT and (config.RVC_ROOT / "tools" / "infer_cli.py").exists():
                script = config.RVC_ROOT / "tools" / "infer_cli.py"
            else:
                return False

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
        env = os.environ.copy()
        if config.RVC_ROOT:
            env["RVC_ROOT"] = str(config.RVC_ROOT)
        try:
            subprocess.run(cmd, check=True, capture_output=True, env=env, timeout=120)
            return wav_out.exists() and wav_out.stat().st_size > 0
        except Exception as exc:
            logger.info("RVC infer failed: %s", exc)
            return False


def rvc_status() -> dict:
    weights = sorted(p.name for p in config.RVC_WEIGHTS.glob("*.pth")) if config.RVC_WEIGHTS.exists() else []
    return {
        "configured_root": str(config.RVC_ROOT) if config.RVC_ROOT else None,
        "weights_dir": str(config.RVC_WEIGHTS),
        "weights": weights,
        "infer_script": str(config.RVC_INFER_SCRIPT) if config.RVC_INFER_SCRIPT else None,
        "available": bool(weights) and (
            bool(config.RVC_INFER_SCRIPT and Path(config.RVC_INFER_SCRIPT).exists())
            or bool(config.RVC_ROOT and (config.RVC_ROOT / "tools" / "infer_cli.py").exists())
        ),
        "note": (
            "RVC converts TTS audio timbre; it does not synthesize speech from text. "
            "Without a working infer script, LokalReader falls back to LocalTTS with "
            "distinct system / espeak voices per character."
        ),
    }
