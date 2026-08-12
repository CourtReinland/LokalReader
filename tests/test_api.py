from pathlib import Path

from fastapi.testclient import TestClient

from lokalreader.main import app

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"


def test_health_and_upload_playback():
    client = TestClient(app)
    assert client.get("/api/health").json()["ok"] is True

    voices = client.get("/api/voices").json()
    assert voices["piper"]["available"] is True or voices["local_tts"]["engine"] == "piper"
    # Never offer macOS system voices
    for v in voices.get("voices") or []:
        assert not v["id"].startswith("mac:")
        assert not v["id"].startswith("espeak:")
        assert v["engine"] in {"rvc", "piper_emergency"}

    with (SAMPLES / "the_quiet_carriage.txt").open("rb") as fh:
        res = client.post("/api/books", files={"file": ("the_quiet_carriage.txt", fh, "text/plain")})
    assert res.status_code == 200, res.text
    payload = res.json()
    book = payload["book"]
    assert book["meta"]["kind"] == "fiction"
    assert book["meta"]["segment_count"] > 0

    book_id = book["meta"]["id"]
    # Default mapping should prefer rvc:* when weights exist (make test creates stubs)
    mapping = payload["mapping"]
    if mapping.get("narrator_voice"):
        assert mapping["narrator_voice"].startswith("rvc:") or mapping["narrator_voice"].startswith(
            "piper:"
        )

    synth = client.post(
        "/api/playback/synthesize",
        json={"book_id": book_id, "segment_ids": [book["segments"][0]["id"]], "speed": 1.0},
    )
    assert synth.status_code == 200, synth.text
    segments = synth.json()["segments"]
    assert segments
    assert segments[0]["voice_id"].startswith("rvc:") or segments[0]["voice_id"].startswith("piper:")
    audio = client.get(segments[0]["audio_url"])
    assert audio.status_code == 200
    assert len(audio.content) > 100


def test_voices_status_has_setup_fields():
    client = TestClient(app)
    data = client.get("/api/voices").json()
    assert "rvc" in data
    assert "missing" in data
    assert "setup_hint" in data or data.get("ready") is True
    assert "Samantha" not in (data.get("rvc") or {}).get("note", "")
