import wave
from pathlib import Path

import pytest

from lokalreader import config
from lokalreader.voices.errors import VoiceSetupError
from lokalreader.voices.piper_tts import (
    PiperTTSBackend,
    _is_speakable,
    write_silence_wav,
)
from lokalreader.voices.rvc import RVCVoiceBackend, rvc_status
from lokalreader.voices.service import VoiceService


def test_no_macos_or_espeak_voices_listed():
    svc = VoiceService()
    ids = [v.id for v in svc.list_voices()]
    assert all(not i.startswith("mac:") for i in ids)
    assert all(not i.startswith("espeak:") for i in ids)
    # User-facing engines are rvc (and optionally emergency piper)
    for v in svc.list_voices():
        assert v.engine in {"rvc", "piper_emergency"}


def test_piper_available_and_synthesize(tmp_path: Path):
    backend = PiperTTSBackend()
    if not backend.available():
        pytest.skip("Piper voices not installed (make test downloads them)")
    voices = backend.list_voices()
    assert voices
    out = tmp_path / "hello.wav"
    backend.synthesize("Hello from LokalReader.", voices[0].id, out, speed=1.0)
    assert out.exists()
    assert out.stat().st_size > 100


def test_is_speakable_rejects_separators():
    assert _is_speakable("Hello")
    assert _is_speakable("Chapter 12")
    assert not _is_speakable("")
    assert not _is_speakable("―")
    assert not _is_speakable("—")
    assert not _is_speakable("…")
    assert not _is_speakable("***")
    assert not _is_speakable("  ―  ")
    assert not _is_speakable("*** * ―")


def test_write_silence_wav_has_channels(tmp_path: Path):
    out = tmp_path / "silence.wav"
    write_silence_wav(out, duration_sec=0.2)
    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 22050
        assert wf.getnframes() > 0


def test_piper_separator_segment_writes_silence(tmp_path: Path):
    """Regression: manuscript '―' must not 500 with '# channels not specified'."""
    backend = PiperTTSBackend()
    # Silence path does not require Piper to be installed
    out = tmp_path / "sep.wav"
    backend.synthesize("―", "piper:en_US-lessac-medium", out)
    assert out.exists()
    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getnframes() > 0


def test_rvc_status_shape():
    status = rvc_status()
    assert "available" in status
    assert "weights_dir" in status
    assert "note" in status
    assert "state" in status
    assert "missing" in status


def test_rvc_pipeline_with_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Full text → Piper → stub RVC path (wiring). Never macOS say."""
    if not PiperTTSBackend().available():
        pytest.skip("Piper not ready")
    root = Path(__file__).resolve().parents[1]
    weights = tmp_path / "weights"
    weights.mkdir()
    (weights / "narrator.pth").write_bytes(b"RVC-TEST-WEIGHT")
    (weights / "narrator.json").write_text(
        '{"role":"narrator","gender":"male"}', encoding="utf-8"
    )
    monkeypatch.setattr(config, "RVC_WEIGHTS", weights)
    monkeypatch.setattr(config, "RVC_INFER_SCRIPT", root / "scripts" / "rvc_infer_stub.py")
    monkeypatch.setattr(config, "RVC_PYTHON", "python3")
    monkeypatch.setattr(config, "ALLOW_EMERGENCY_TTS", False)

    backend = RVCVoiceBackend()
    assert any(v.id == "rvc:narrator" for v in backend.list_voices())
    out = tmp_path / "converted.wav"
    backend.synthesize("Stub conversion path.", "rvc:narrator", out)
    assert out.exists() and out.stat().st_size > 100


def test_rvc_fails_loudly_without_model(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config, "RVC_WEIGHTS", tmp_path / "empty_weights")
    monkeypatch.setattr(config, "ALLOW_EMERGENCY_TTS", False)
    (tmp_path / "empty_weights").mkdir()
    backend = RVCVoiceBackend()
    with pytest.raises(VoiceSetupError) as exc:
        backend.synthesize("Nope.", "rvc:missing_model", tmp_path / "x.wav")
    assert "make setup-voices" in str(exc.value).lower() or "missing" in str(exc.value).lower()
    assert "Samantha" not in str(exc.value)


def test_legacy_mac_voice_rejected(monkeypatch: pytest.MonkeyPatch):
    from lokalreader.models import Segment, SegmentKind, VoiceMapping

    monkeypatch.setattr(config, "ALLOW_EMERGENCY_TTS", False)
    svc = VoiceService()
    seg = Segment(
        id="s1",
        chapter_id="c1",
        order=0,
        kind=SegmentKind.narration,
        speaker="Narrator",
        text="Hello",
    )
    mapping = VoiceMapping(book_id="b", narrator_voice="mac:Samantha", use_rvc=False)
    with pytest.raises(VoiceSetupError) as exc:
        svc.synthesize_segment("b", seg, mapping)
    assert "mac:" in str(exc.value) or "Legacy" in str(exc.value)
