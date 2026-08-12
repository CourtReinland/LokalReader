"""Voice backends: Piper neural TTS → optional RVC timbre conversion."""

from lokalreader.voices.errors import VoiceSetupError
from lokalreader.voices.piper_tts import PiperTTSBackend
from lokalreader.voices.rvc import RVCVoiceBackend
from lokalreader.voices.service import VoiceService

__all__ = [
    "VoiceService",
    "PiperTTSBackend",
    "RVCVoiceBackend",
    "VoiceSetupError",
]
