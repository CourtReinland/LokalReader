from pathlib import Path

from fastapi.testclient import TestClient

from lokalreader.main import app

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"


def test_health_and_upload_playback():
    client = TestClient(app)
    assert client.get("/api/health").json()["ok"] is True

    voices = client.get("/api/voices").json()
    assert voices["local_tts"]["available"] is True
    assert voices["voices"]

    with (SAMPLES / "the_quiet_carriage.txt").open("rb") as fh:
        res = client.post("/api/books", files={"file": ("the_quiet_carriage.txt", fh, "text/plain")})
    assert res.status_code == 200, res.text
    payload = res.json()
    book = payload["book"]
    assert book["meta"]["kind"] == "fiction"
    assert book["meta"]["segment_count"] > 0

    book_id = book["meta"]["id"]
    synth = client.post(
        "/api/playback/synthesize",
        json={"book_id": book_id, "segment_ids": [book["segments"][0]["id"]], "speed": 1.0},
    )
    assert synth.status_code == 200, synth.text
    segments = synth.json()["segments"]
    assert segments
    audio = client.get(segments[0]["audio_url"])
    assert audio.status_code == 200
    assert len(audio.content) > 100
