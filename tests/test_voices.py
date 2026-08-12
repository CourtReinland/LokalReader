from pathlib import Path

from lokalreader.voices.local_tts import LocalTTSBackend
from lokalreader.voices.rvc import RVCVoiceBackend, rvc_status


def test_local_tts_available_and_lists_voices():
    backend = LocalTTSBackend()
    assert backend.available()
    voices = backend.list_voices()
    assert voices
    assert all(v.id for v in voices)


def test_local_tts_synthesize(tmp_path: Path):
    backend = LocalTTSBackend()
    out = tmp_path / "hello.wav"
    voice = backend.list_voices()[0].id
    backend.synthesize("Hello from LokalReader.", voice, out, speed=1.0)
    assert out.exists()
    assert out.stat().st_size > 100


def test_rvc_status_shape():
    status = rvc_status()
    assert "available" in status
    assert "weights_dir" in status
    assert "note" in status


def test_rvc_falls_back_without_script(tmp_path: Path):
    backend = RVCVoiceBackend()
    out = tmp_path / "fallback.wav"
    # Even with an rvc: id and no models/script, synthesize should not crash —
    # missing model causes base path via failed conversion / or we use base id.
    # Use a local voice id through RVC wrapper.
    voice = backend.base.list_voices()[0].id
    backend.synthesize("Fallback path.", voice, out)
    assert out.exists()
