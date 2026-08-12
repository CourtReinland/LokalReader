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


def test_synthesize_respects_limit_and_has_more():
    """from_segment_id must not convert the whole book in one call."""
    client = TestClient(app)
    with (SAMPLES / "the_quiet_carriage.txt").open("rb") as fh:
        res = client.post("/api/books", files={"file": ("the_quiet_carriage.txt", fh, "text/plain")})
    assert res.status_code == 200, res.text
    book = res.json()["book"]
    book_id = book["meta"]["id"]
    segs = book["segments"]
    assert len(segs) >= 2

    first_id = segs[0]["id"]
    limited = client.post(
        "/api/playback/synthesize",
        json={"book_id": book_id, "from_segment_id": first_id, "limit": 1, "speed": 1.0},
    )
    assert limited.status_code == 200, limited.text
    body = limited.json()
    assert body["count"] == 1
    assert body["limit"] == 1
    assert body["total_matched"] == len(segs)
    assert body["has_more"] is True
    assert body["next_from_segment_id"] == segs[1]["id"]
    assert body["segments"][0]["segment_id"] == first_id

    # Open-ended from_segment_id without limit is still capped (default batch)
    uncapped = client.post(
        "/api/playback/synthesize",
        json={"book_id": book_id, "from_segment_id": first_id, "speed": 1.0},
    )
    assert uncapped.status_code == 200, uncapped.text
    ubody = uncapped.json()
    assert ubody["count"] <= ubody["limit"]
    assert ubody["count"] < len(segs) or not ubody["has_more"]


def test_synthesize_segment_ids_batch():
    client = TestClient(app)
    with (SAMPLES / "the_quiet_carriage.txt").open("rb") as fh:
        res = client.post("/api/books", files={"file": ("the_quiet_carriage.txt", fh, "text/plain")})
    book = res.json()["book"]
    ids = [s["id"] for s in book["segments"][:3]]
    synth = client.post(
        "/api/playback/synthesize",
        json={"book_id": book["meta"]["id"], "segment_ids": ids, "limit": 6, "speed": 1.0},
    )
    assert synth.status_code == 200, synth.text
    body = synth.json()
    assert body["count"] == len(ids)
    assert [s["segment_id"] for s in body["segments"]] == ids
    assert body["has_more"] is False
