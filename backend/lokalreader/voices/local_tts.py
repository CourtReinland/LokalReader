"""Local offline TTS: macOS `say` (+ afconvert), else espeak-ng."""

from __future__ import annotations

import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from lokalreader.models import VoiceInfo
from lokalreader.voices.base import VoiceBackend

# Distinct character variants when RVC is unavailable.
# On macOS these map to system voice names; on Linux to espeak voice+variant.
MAC_VOICES: list[dict] = [
    {"id": "mac:Alex", "name": "Alex", "gender": "male", "description": "macOS system — clear male narrator"},
    {"id": "mac:Samantha", "name": "Samantha", "gender": "female", "description": "macOS system — warm female"},
    {"id": "mac:Daniel", "name": "Daniel", "gender": "male", "description": "macOS system — British male"},
    {"id": "mac:Karen", "name": "Karen", "gender": "female", "description": "macOS system — Australian female"},
    {"id": "mac:Moira", "name": "Moira", "gender": "female", "description": "macOS system — Irish female"},
    {"id": "mac:Fred", "name": "Fred", "gender": "male", "description": "macOS system — classic male"},
    {"id": "mac:Victoria", "name": "Victoria", "gender": "female", "description": "macOS system — crisp female"},
    {"id": "mac:Oliver", "name": "Oliver", "gender": "male", "description": "macOS system — British male"},
]

ESPEAK_VOICES: list[dict] = [
    {"id": "espeak:en+m3", "name": "Narrator (en m3)", "gender": "male", "pitch": 0, "rate": 1.0, "description": "espeak-ng male, steady"},
    {"id": "espeak:en+f3", "name": "Ava (en f3)", "gender": "female", "pitch": 20, "rate": 1.0, "description": "espeak-ng female"},
    {"id": "espeak:en+m1", "name": "Ben (en m1)", "gender": "male", "pitch": -10, "rate": 0.95, "description": "espeak-ng deeper male"},
    {"id": "espeak:en+f2", "name": "Clara (en f2)", "gender": "female", "pitch": 35, "rate": 1.05, "description": "espeak-ng brighter female"},
    {"id": "espeak:en+m2", "name": "Drew (en m2)", "gender": "male", "pitch": 10, "rate": 1.1, "description": "espeak-ng quicker male"},
    {"id": "espeak:en-gb+m3", "name": "Elliot (en-gb)", "gender": "male", "pitch": 0, "rate": 1.0, "description": "espeak-ng British male"},
    {"id": "espeak:en-us+f3", "name": "Faith (en-us f3)", "gender": "female", "pitch": 15, "rate": 1.0, "description": "espeak-ng US female"},
    {"id": "espeak:en+f1", "name": "Greta (en f1)", "gender": "female", "pitch": 5, "rate": 0.92, "description": "espeak-ng lower female"},
]


class LocalTTSBackend(VoiceBackend):
    name = "local_tts"

    def __init__(self) -> None:
        self.system = platform.system()
        self._say = shutil.which("say")
        self._afconvert = shutil.which("afconvert")
        self._espeak = shutil.which("espeak-ng") or shutil.which("espeak")
        self._ffmpeg = shutil.which("ffmpeg")

    def available(self) -> bool:
        if self.system == "Darwin" and self._say:
            return True
        return bool(self._espeak)

    def list_voices(self) -> list[VoiceInfo]:
        if self.system == "Darwin" and self._say:
            return self._list_mac_voices()
        return [
            VoiceInfo(
                id=v["id"],
                name=v["name"],
                engine="espeak-ng",
                gender=v.get("gender"),
                description=v.get("description", ""),
                pitch=float(v.get("pitch", 0)),
                rate=float(v.get("rate", 1.0)),
            )
            for v in ESPEAK_VOICES
        ]

    def _list_mac_voices(self) -> list[VoiceInfo]:
        installed = self._mac_installed_voices()
        voices: list[VoiceInfo] = []
        for v in MAC_VOICES:
            short = v["name"]
            if installed and short not in installed and short.lower() not in {x.lower() for x in installed}:
                continue
            voices.append(
                VoiceInfo(
                    id=v["id"],
                    name=v["name"],
                    engine="macos_say",
                    gender=v.get("gender"),
                    description=v.get("description", ""),
                )
            )
        if not voices:
            # Fallback: parse `say -v ?`
            for name in installed or ["Alex"]:
                voices.append(
                    VoiceInfo(id=f"mac:{name}", name=name, engine="macos_say", description="macOS system voice")
                )
        return voices

    def _mac_installed_voices(self) -> list[str]:
        if not self._say:
            return []
        try:
            proc = subprocess.run(
                [self._say, "-v", "?"],
                capture_output=True,
                text=True,
                check=False,
            )
            names = []
            for line in (proc.stdout or proc.stderr or "").splitlines():
                # "Alex                en_US    # ..."
                m = re.match(r"^(\S+)\s+", line)
                if m:
                    names.append(m.group(1))
            return names
        except Exception:
            return []

    def synthesize(self, text: str, voice_id: str, out_path: Path, *, speed: float = 1.0) -> Path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        clean = _sanitize_text(text)
        if not clean:
            clean = "…"
        if voice_id.startswith("mac:") or (self.system == "Darwin" and self._say and not voice_id.startswith("espeak:")):
            return self._synth_mac(clean, voice_id, out_path, speed=speed)
        return self._synth_espeak(clean, voice_id, out_path, speed=speed)

    def _synth_mac(self, text: str, voice_id: str, out_path: Path, *, speed: float) -> Path:
        if not self._say:
            raise RuntimeError("macOS `say` not found")
        voice = voice_id.split(":", 1)[-1]
        # say -r is words per minute; default ~175
        rate = max(80, min(350, int(175 * speed)))
        with tempfile.TemporaryDirectory() as tmp:
            aiff = Path(tmp) / "out.aiff"
            cmd = [self._say, "-v", voice, "-r", str(rate), "-o", str(aiff), text]
            subprocess.run(cmd, check=True, capture_output=True)
            if self._afconvert:
                subprocess.run(
                    [self._afconvert, "-f", "WAVE", "-d", "LEI16@22050", str(aiff), str(out_path)],
                    check=True,
                    capture_output=True,
                )
            elif self._ffmpeg:
                subprocess.run(
                    [self._ffmpeg, "-y", "-i", str(aiff), "-ar", "22050", "-ac", "1", str(out_path)],
                    check=True,
                    capture_output=True,
                )
            else:
                # Last resort: copy aiff with wav extension (may not play everywhere)
                out_path.write_bytes(aiff.read_bytes())
        return out_path

    def _synth_espeak(self, text: str, voice_id: str, out_path: Path, *, speed: float) -> Path:
        if not self._espeak:
            raise RuntimeError(
                "No local TTS found. On macOS, `say` is required. "
                "On Linux, install espeak-ng (e.g. `brew install espeak` / `apt install espeak-ng`)."
            )
        voice = voice_id.split(":", 1)[-1] if ":" in voice_id else "en"
        meta = next((v for v in ESPEAK_VOICES if v["id"] == voice_id), None)
        pitch = int(meta.get("pitch", 0)) if meta else 0
        base_wpm = 160 * float(meta.get("rate", 1.0) if meta else 1.0) * speed
        wpm = max(80, min(300, int(base_wpm)))
        wav_tmp = out_path.with_suffix(".raw.wav")
        cmd = [
            self._espeak,
            "-v",
            voice,
            "-s",
            str(wpm),
            "-p",
            str(max(0, min(99, 50 + pitch))),
            "-w",
            str(wav_tmp),
            text,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        if self._ffmpeg and wav_tmp != out_path:
            subprocess.run(
                [self._ffmpeg, "-y", "-i", str(wav_tmp), "-ar", "22050", "-ac", "1", str(out_path)],
                check=True,
                capture_output=True,
            )
            wav_tmp.unlink(missing_ok=True)
        else:
            wav_tmp.replace(out_path)
        return out_path


def _sanitize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    # Avoid shell/say quirks with brackets
    return text[:4000]
