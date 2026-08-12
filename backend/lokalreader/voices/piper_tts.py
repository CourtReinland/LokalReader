"""Local neural TTS via Piper (ONNX) — base synthesizer for the RVC pipeline.

RVC does not synthesize from text. Piper produces the source WAV; RVC converts timbre.
macOS `say` / espeak are intentionally not offered as user-facing voices.
"""

from __future__ import annotations

import logging
import re
import wave
from pathlib import Path

from lokalreader import config
from lokalreader.models import VoiceInfo
from lokalreader.voices.base import VoiceBackend
from lokalreader.voices.errors import VoiceSetupError

logger = logging.getLogger(__name__)

# Curated English voices for fiction base synthesis (gender-matched into RVC).
PIPER_CATALOG: list[dict] = [
    {
        "id": "piper:en_US-lessac-medium",
        "slug": "en_US-lessac-medium",
        "name": "Lessac (neural base)",
        "gender": "male",
        "description": "Piper en_US medium — clear male base for RVC",
    },
    {
        "id": "piper:en_US-amy-medium",
        "slug": "en_US-amy-medium",
        "name": "Amy (neural base)",
        "gender": "female",
        "description": "Piper en_US medium — warm female base for RVC",
    },
    {
        "id": "piper:en_GB-alan-medium",
        "slug": "en_GB-alan-medium",
        "name": "Alan (neural base)",
        "gender": "male",
        "description": "Piper en_GB medium — British male base",
    },
    {
        "id": "piper:en_US-joe-medium",
        "slug": "en_US-joe-medium",
        "name": "Joe (neural base)",
        "gender": "male",
        "description": "Piper en_US medium — alternate male base",
    },
]


class PiperTTSBackend(VoiceBackend):
    name = "piper"

    def __init__(self) -> None:
        self._voices_dir = config.PIPER_VOICES_DIR
        self._loaded: dict[str, object] = {}

    def available(self) -> bool:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False
        return bool(self._installed_slugs())

    def setup_status(self) -> dict:
        try:
            import piper  # noqa: F401

            package_ok = True
        except ImportError:
            package_ok = False
        installed = self._installed_slugs()
        missing = []
        if not package_ok:
            missing.append("piper-tts package (pip install piper-tts / make install)")
        if not installed:
            missing.append(
                f"Piper voice models in {self._voices_dir} "
                f"(make setup-voices downloads {config.PIPER_DEFAULT_VOICE})"
            )
        return {
            "available": package_ok and bool(installed),
            "engine": "piper",
            "package_installed": package_ok,
            "voices_dir": str(self._voices_dir),
            "installed_voices": installed,
            "missing": missing,
            "setup_hint": None if not missing else "Run `make setup-voices`.",
        }

    def list_voices(self) -> list[VoiceInfo]:
        """Internal catalog of installed Piper voices (not user-facing by default)."""
        installed = set(self._installed_slugs())
        voices: list[VoiceInfo] = []
        for v in PIPER_CATALOG:
            if v["slug"] not in installed:
                continue
            voices.append(
                VoiceInfo(
                    id=v["id"],
                    name=v["name"],
                    engine="piper",
                    gender=v.get("gender"),
                    description=v.get("description", ""),
                )
            )
        # Include any extra .onnx voices found on disk
        for slug in installed:
            vid = f"piper:{slug}"
            if any(x.id == vid for x in voices):
                continue
            voices.append(
                VoiceInfo(
                    id=vid,
                    name=slug,
                    engine="piper",
                    description="Piper ONNX voice",
                )
            )
        return voices

    def base_voice_for_gender(self, gender: str | None) -> str:
        voices = {v.id: v for v in self.list_voices()}
        female = f"piper:{config.PIPER_FEMALE_VOICE}"
        male = f"piper:{config.PIPER_MALE_VOICE}"
        default = f"piper:{config.PIPER_DEFAULT_VOICE}"
        if gender == "female" and female in voices:
            return female
        if gender == "male" and male in voices:
            return male
        if default in voices:
            return default
        if voices:
            return next(iter(voices))
        raise VoiceSetupError(
            "No Piper neural TTS voices installed.",
            missing=[f"voice models under {self._voices_dir}"],
        )

    def synthesize(self, text: str, voice_id: str, out_path: Path, *, speed: float = 1.0) -> Path:
        status = self.setup_status()
        if not status["available"]:
            raise VoiceSetupError(
                "Piper neural TTS is not ready.",
                missing=status["missing"],
            )
        slug = voice_id.split(":", 1)[-1] if voice_id.startswith("piper:") else voice_id
        model_path = self._model_path(slug)
        if model_path is None:
            raise VoiceSetupError(
                f"Piper voice '{slug}' not found.",
                missing=[f"{slug}.onnx (+ .onnx.json) in {self._voices_dir}"],
            )
        clean = _sanitize_text(text)
        if not clean:
            clean = "…"
        voice = self._get_voice(slug, model_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # length_scale: >1 slower; Piper uses length_scale inversely to speaking rate
        length_scale = 1.0 / max(0.5, min(2.0, speed))
        try:
            from piper.config import SynthesisConfig

            syn_config = SynthesisConfig(length_scale=length_scale)
            with wave.open(str(out_path), "wb") as wav_file:
                voice.synthesize_wav(clean, wav_file, syn_config=syn_config)
        except ImportError:
            # Older piper API without SynthesisConfig
            with wave.open(str(out_path), "wb") as wav_file:
                voice.synthesize_wav(clean, wav_file)
        if not out_path.exists() or out_path.stat().st_size < 44:
            raise VoiceSetupError(f"Piper produced empty audio for voice '{slug}'.")
        return out_path

    def _installed_slugs(self) -> list[str]:
        root = self._voices_dir
        if not root.exists():
            return []
        slugs = sorted({p.stem for p in root.glob("*.onnx")})
        return slugs

    def _model_path(self, slug: str) -> Path | None:
        candidate = self._voices_dir / f"{slug}.onnx"
        if candidate.is_file():
            return candidate
        # Nested download layout: voices_dir/en_US-lessac-medium/en_US-lessac-medium.onnx
        nested = self._voices_dir / slug / f"{slug}.onnx"
        if nested.is_file():
            return nested
        matches = list(self._voices_dir.rglob(f"{slug}.onnx"))
        return matches[0] if matches else None

    def _get_voice(self, slug: str, model_path: Path):
        if slug in self._loaded:
            return self._loaded[slug]
        from piper import PiperVoice

        voice = PiperVoice.load(str(model_path))
        self._loaded[slug] = voice
        return voice


def _sanitize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text[:4000]
