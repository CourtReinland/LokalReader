"""Voice catalog + segment synthesis with caching."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lokalreader import config
from lokalreader.models import Segment, SegmentKind, SynthesizeResult, VoiceInfo, VoiceMapping
from lokalreader.voices.errors import VoiceSetupError
from lokalreader.voices.piper_tts import PiperTTSBackend
from lokalreader.voices.rvc import RVCVoiceBackend, rvc_status


class VoiceService:
    def __init__(self) -> None:
        self.piper = PiperTTSBackend()
        self.rvc = RVCVoiceBackend(self.piper)

    def list_voices(self) -> list[VoiceInfo]:
        """User-facing voices: RVC models only (plus emergency piper:* if enabled)."""
        voices = self.rvc.list_voices()
        if config.ALLOW_EMERGENCY_TTS:
            for v in self.piper.list_voices():
                voices.append(
                    VoiceInfo(
                        id=v.id,
                        name=f"Emergency · {v.name}",
                        engine="piper_emergency",
                        gender=v.gender,
                        description=(
                            "EMERGENCY / CI only — Piper without RVC. "
                            "Disabled by default (LOKALREADER_ALLOW_EMERGENCY_TTS)."
                        ),
                    )
                )
        return voices

    def status(self) -> dict:
        piper_status = self.piper.setup_status()
        rvc = rvc_status()
        voices = self.list_voices()
        ready = bool(voices) and (
            rvc.get("available") or (config.ALLOW_EMERGENCY_TTS and piper_status.get("available"))
        )
        missing = []
        if not piper_status.get("available"):
            missing.extend(piper_status.get("missing") or [])
        if not rvc.get("available") and not config.ALLOW_EMERGENCY_TTS:
            missing.extend(rvc.get("missing") or [])
        if not voices:
            missing.append("No rvc:* voices — place .pth models in data/rvc_weights/")

        return {
            "ready": ready,
            "setup_hint": None
            if ready
            else "Run `make setup-voices` then restart. System voices (macOS say / espeak) are not used.",
            "missing": missing,
            "piper": piper_status,
            "local_tts": {
                # Back-compat key for older clients — now Piper, never macos_say
                "available": piper_status.get("available"),
                "engine": "piper",
                "platform": piper_status.get("voices_dir"),
            },
            "rvc": rvc,
            "emergency_tts_enabled": config.ALLOW_EMERGENCY_TTS,
            "voices": [v.model_dump() for v in voices],
        }

    def default_mapping_for(
        self,
        book_id: str,
        characters: list[str],
        use_rvc: bool = True,
    ) -> VoiceMapping:
        voices = self.list_voices()
        rvc_voices = [v for v in voices if v.engine == "rvc"]
        emergency = [v for v in voices if v.engine == "piper_emergency"]

        if rvc_voices:
            narrator = _pick_role(rvc_voices, "narrator") or rvc_voices[0].id
            pool = [v for v in rvc_voices if v.id != narrator] or rvc_voices
            char_map: dict[str, str] = {}
            for i, name in enumerate(characters):
                char_map[name] = pool[i % len(pool)].id
            return VoiceMapping(
                book_id=book_id,
                narrator_voice=narrator,
                character_voices=char_map,
                use_rvc=True,
            )

        if config.ALLOW_EMERGENCY_TTS and emergency:
            narrator = emergency[0].id
            char_map = {
                name: emergency[(i + 1) % len(emergency)].id for i, name in enumerate(characters)
            }
            return VoiceMapping(
                book_id=book_id,
                narrator_voice=narrator,
                character_voices=char_map,
                use_rvc=False,
            )

        # Empty mapping — synthesize will raise a clear VoiceSetupError
        return VoiceMapping(
            book_id=book_id,
            narrator_voice="",
            character_voices={},
            use_rvc=use_rvc,
        )

    def voice_for_segment(self, segment: Segment, mapping: VoiceMapping) -> str:
        if segment.kind == SegmentKind.dialogue:
            return mapping.character_voices.get(segment.speaker) or mapping.narrator_voice
        return mapping.narrator_voice

    def synthesize_segment(
        self,
        book_id: str,
        segment: Segment,
        mapping: VoiceMapping,
        *,
        speed: float | None = None,
    ) -> SynthesizeResult:
        config.ensure_dirs()
        voice_id = self.voice_for_segment(segment, mapping)
        if not voice_id:
            status = self.status()
            raise VoiceSetupError(
                "No voice assigned. Artistic path requires RVC models.",
                missing=status.get("missing")
                or ["rvc:*.pth in data/rvc_weights — run make setup-voices"],
            )
        # Reject legacy mac/espeak ids if somehow stored in old mappings
        if voice_id.startswith("mac:") or voice_id.startswith("espeak:"):
            raise VoiceSetupError(
                f"Legacy system voice '{voice_id}' is disabled. "
                "Re-open Voices and assign an rvc:<model> voice.",
                missing=["updated voice mapping"],
            )

        rate = speed if speed is not None else mapping.speed
        cache_key = hashlib.sha1(
            f"{segment.id}|{segment.text}|{voice_id}|{rate:.3f}".encode("utf-8")
        ).hexdigest()[:16]
        out_dir = config.AUDIO_DIR / book_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{segment.id}_{cache_key}.wav"
        cached = out_path.exists()
        if not cached:
            if voice_id.startswith("rvc:"):
                self.rvc.synthesize(segment.text, voice_id, out_path, speed=rate)
            elif voice_id.startswith("piper:") and config.ALLOW_EMERGENCY_TTS:
                self.piper.synthesize(segment.text, voice_id, out_path, speed=rate)
            else:
                raise VoiceSetupError(
                    f"Cannot synthesize with voice '{voice_id}'.",
                    missing=["rvc:<model> assignment"],
                )
        return SynthesizeResult(
            segment_id=segment.id,
            audio_url=f"/api/audio/{book_id}/{out_path.name}",
            voice_id=voice_id,
            cached=cached,
        )


def _pick_role(voices: list[VoiceInfo], role: str) -> str | None:
    role_l = role.lower()
    for v in voices:
        if v.rvc_model and role_l in v.rvc_model.lower():
            return v.id
        if role_l in (v.name or "").lower():
            return v.id
    return None
