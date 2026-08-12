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
        out_path.parent.mkdir(parents=True, exist_ok=True)
        clean = _sanitize_text(text)
        # Manuscript separators (―, …, *** ) have no phonemes — Piper leaves the WAV
        # header incomplete ("# channels not specified"). Write silence instead.
        if not _is_speakable(clean):
            logger.info("Piper skip non-speech text %r → silence wav", (text or "")[:40])
            return write_silence_wav(out_path)

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
        voice = self._get_voice(slug, model_path)
        # length_scale: >1 slower; Piper uses length_scale inversely to speaking rate
        length_scale = 1.0 / max(0.5, min(2.0, speed))
        try:
            try:
                from piper.config import SynthesisConfig

                syn_config = SynthesisConfig(length_scale=length_scale)
                with wave.open(str(out_path), "wb") as wav_file:
                    voice.synthesize_wav(clean, wav_file, syn_config=syn_config)
            except ImportError:
                # Older piper API without SynthesisConfig
                with wave.open(str(out_path), "wb") as wav_file:
                    voice.synthesize_wav(clean, wav_file)
        except Exception as exc:
            # One bad segment must not 500 an entire playback batch.
            logger.warning(
                "Piper failed for %r (%s) — writing silence fallback",
                clean[:60],
                exc,
            )
            return write_silence_wav(out_path)

        if not out_path.exists() or out_path.stat().st_size < 44:
            logger.warning("Piper produced empty audio for %r — silence fallback", clean[:60])
            return write_silence_wav(out_path)
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
    text = re.sub(r"\s+", " ", text or "").strip()
    return text[:4000]


def _is_speakable(text: str) -> bool:
    """True if text has at least one alphanumeric character.

    Punctuation-only manuscript separators (―, —, ***, …) are not speakable and
    cause Piper to fail with incomplete WAV headers ("# channels not specified").
    """
    if not text:
        return False
    return any(ch.isalnum() for ch in text)


def write_silence_wav(
    out_path: Path,
    *,
    duration_sec: float = 0.35,
    sample_rate: int = 22050,
    sample_width: int = 2,
    channels: int = 1,
) -> Path:
    """Write a valid short mono PCM silence WAV (fully specified channels/rate)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n_frames = max(1, int(sample_rate * duration_sec))
    with wave.open(str(out_path), "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(sample_width)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00" * (n_frames * sample_width * channels))
    return out_path
