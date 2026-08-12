"""VoiceBackend interface — Piper neural TTS, then RVC timbre post-pass."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from lokalreader.models import VoiceInfo


class VoiceBackend(ABC):
    """Produce speech audio from text.

    Correct architecture:
      1) Piper neural TTS synthesizes WAV from text
      2) RVC converts that WAV into a character timbre (.pth)
    RVC alone cannot synthesize speech from text.
    macOS `say` / espeak are not part of this interface.
    """

    name: str = "base"

    @abstractmethod
    def list_voices(self) -> list[VoiceInfo]:
        raise NotImplementedError

    @abstractmethod
    def synthesize(
        self,
        text: str,
        voice_id: str,
        out_path: Path,
        *,
        speed: float = 1.0,
    ) -> Path:
        """Synthesize `text` with `voice_id` into `out_path` (wav)."""
        raise NotImplementedError

    def available(self) -> bool:
        return True
