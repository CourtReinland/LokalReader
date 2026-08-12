import wave
from pathlib import Path

import pytest

from lokalreader import config
from lokalreader.voices.errors import VoiceSetupError
from lokalreader.voices.piper_tts import PiperTTSBackend, _sanitize_text, _write_silence
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


def test_sanitize_text_rejects_separators():
    assert _sanitize_text("Hello") == "Hello"
    assert _sanitize_text("Chapter 12") == "Chapter 12"
    assert _sanitize_text("café") == "café"  # Latin-1 letter
    assert _sanitize_text("") == ""
    assert _sanitize_text("---") == ""
    assert _sanitize_text("―") == ""
    assert _sanitize_text("—") == ""
    assert _sanitize_text("…") == ""
    assert _sanitize_text("***") == ""
    assert _sanitize_text("  ―  ") == ""


def test_write_silence_has_channels(tmp_path: Path):
    out = tmp_path / "silence.wav"
    _write_silence(out, seconds=0.25, rate=22050)
    with wave.open(str(out), "rb") as wf:
        assert wf.getnchannels() == 1
        assert wf.getsampwidth() == 2
        assert wf.getframerate() == 22050
        assert wf.getnframes() > 0


def test_piper_separator_writes_silence_not_ellipsis(tmp_path: Path):
    """Regression: '―' / '---' must not 500 with '# channels not specified'."""
    backend = PiperTTSBackend()
    for text in ("―", "---", "***"):
        out = tmp_path / f"sep_{hash(text)}.wav"
        backend.synthesize(text, "piper:en_US-lessac-medium", out)
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
