"""Voice catalog + segment synthesis with caching."""

from __future__ import annotations

import hashlib
from pathlib import Path

from lokalreader import config
from lokalreader.models import Segment, SegmentKind, SynthesizeResult, VoiceInfo, VoiceMapping
from lokalreader.voices.local_tts import LocalTTSBackend
from lokalreader.voices.rvc import RVCVoiceBackend, rvc_status


class VoiceService:
    def __init__(self) -> None:
        self.local = LocalTTSBackend()
        self.rvc = RVCVoiceBackend(self.local)

    def list_voices(self) -> list[VoiceInfo]:
        voices = self.local.list_voices()
        # Append RVC model voices when weights exist (even if infer script missing —
        # UI can show them; synthesize will fall back).
        seen = {v.id for v in voices}
        for v in self.rvc.list_voices():
            if v.id not in seen and v.engine == "rvc":
                voices.append(v)
        return voices

    def status(self) -> dict:
        return {
            "local_tts": {
                "available": self.local.available(),
                "engine": "macos_say" if self.local.system == "Darwin" else "espeak-ng",
                "platform": self.local.system,
            },
            "rvc": rvc_status(),
            "voices": [v.model_dump() for v in self.list_voices()],
        }

    def default_mapping_for(self, book_id: str, characters: list[str], use_rvc: bool = False) -> VoiceMapping:
        voices = self.list_voices()
        local_voices = [v for v in voices if v.engine != "rvc"]
        rvc_voices = [v for v in voices if v.engine == "rvc"]
        narrator = local_voices[0].id if local_voices else ""
        char_map: dict[str, str] = {}
        pool = rvc_voices + local_voices[1:] + local_voices[:1]
        for i, name in enumerate(characters):
            if not pool:
                break
            # Prefer distinct non-narrator voices; optionally RVC first
            if use_rvc and rvc_voices:
                char_map[name] = rvc_voices[i % len(rvc_voices)].id
            else:
                # skip narrator-like first voice when possible
                pick = local_voices[(i + 1) % len(local_voices)].id if local_voices else narrator
                char_map[name] = pick
        return VoiceMapping(
            book_id=book_id,
            narrator_voice=narrator,
            character_voices=char_map,
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
            voices = self.list_voices()
            voice_id = voices[0].id if voices else "espeak:en+m3"
        rate = speed if speed is not None else mapping.speed
        cache_key = hashlib.sha1(
            f"{segment.id}|{segment.text}|{voice_id}|{rate:.3f}".encode("utf-8")
        ).hexdigest()[:16]
        out_dir = config.AUDIO_DIR / book_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{segment.id}_{cache_key}.wav"
        cached = out_path.exists()
        if not cached:
            backend: LocalTTSBackend | RVCVoiceBackend = self.rvc if voice_id.startswith("rvc:") else self.local
            # If RVC requested via mapping but voice is local, stay local
            if mapping.use_rvc and voice_id.startswith("rvc:"):
                backend = self.rvc
            backend.synthesize(segment.text, voice_id, out_path, speed=rate)
        return SynthesizeResult(
            segment_id=segment.id,
            audio_url=f"/api/audio/{book_id}/{out_path.name}",
            voice_id=voice_id,
            cached=cached,
        )
