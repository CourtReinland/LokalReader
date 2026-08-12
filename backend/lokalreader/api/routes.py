"""HTTP API routes."""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from lokalreader import config
from lokalreader.models import PlaybackRequest, SegmentUpdate, VoiceMapping
from lokalreader.parsers.registry import SUPPORTED
from lokalreader.storage.library import Library
from lokalreader.voices.errors import VoiceSetupError
from lokalreader.voices.service import VoiceService

router = APIRouter(prefix="/api")
library = Library()
voices = VoiceService()


@router.get("/health")
def health() -> dict:
    return {"ok": True, "service": "LokalReader"}


@router.get("/demo/sample")
def demo_sample():
    """Serve the bundled fiction sample for one-click demos."""
    path = config.ROOT / "samples" / "the_quiet_carriage.txt"
    if not path.exists():
        raise HTTPException(404, "Sample not found")
    return FileResponse(path, media_type="text/plain", filename=path.name)


@router.get("/voices")
def list_voices() -> dict:
    return voices.status()


@router.get("/books")
def list_books() -> list[dict]:
    return [b.model_dump() for b in library.list_books()]


@router.post("/books")
async def upload_book(file: UploadFile = File(...)) -> dict:
    if not file.filename:
        raise HTTPException(400, "Missing filename")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED:
        raise HTTPException(400, f"Unsupported type {suffix}. Supported: {sorted(SUPPORTED)}")
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        doc = library.ingest(tmp_path, Path(file.filename).name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        tmp_path.unlink(missing_ok=True)

    mapping = library.get_mapping(doc.meta.id)
    if not mapping.narrator_voice:
        mapping = voices.default_mapping_for(doc.meta.id, doc.meta.character_names)
        library.save_mapping(mapping)
    return {"book": doc.model_dump(), "mapping": mapping.model_dump()}


@router.get("/books/{book_id}")
def get_book(book_id: str) -> dict:
    try:
        doc = library.get(book_id)
    except KeyError as exc:
        raise HTTPException(404, "Book not found") from exc
    mapping = library.get_mapping(book_id)
    if not mapping.narrator_voice:
        mapping = voices.default_mapping_for(book_id, doc.meta.character_names)
        library.save_mapping(mapping)
    return {"book": doc.model_dump(), "mapping": mapping.model_dump()}


@router.delete("/books/{book_id}")
def delete_book(book_id: str) -> dict:
    library.delete(book_id)
    return {"ok": True}


@router.patch("/books/{book_id}/segments/{segment_id}")
def patch_segment(book_id: str, segment_id: str, update: SegmentUpdate) -> dict:
    try:
        seg = library.update_segment(book_id, segment_id, update)
    except KeyError as exc:
        raise HTTPException(404, "Segment not found") from exc
    return seg.model_dump()


@router.get("/books/{book_id}/mapping")
def get_mapping(book_id: str) -> dict:
    return library.get_mapping(book_id).model_dump()


@router.put("/books/{book_id}/mapping")
def put_mapping(book_id: str, mapping: VoiceMapping) -> dict:
    mapping.book_id = book_id
    return library.save_mapping(mapping).model_dump()


@router.post("/playback/synthesize")
def synthesize(req: PlaybackRequest) -> dict:
    try:
        doc = library.get(req.book_id)
    except KeyError as exc:
        raise HTTPException(404, "Book not found") from exc
    mapping = library.get_mapping(req.book_id)
    if not mapping.narrator_voice:
        mapping = voices.default_mapping_for(req.book_id, doc.meta.character_names)
        library.save_mapping(mapping)

    segs = doc.segments
    if req.segment_ids:
        wanted = set(req.segment_ids)
        segs = [s for s in segs if s.id in wanted]
    elif req.chapter_id:
        segs = [s for s in segs if s.chapter_id == req.chapter_id]
    elif req.from_segment_id:
        start = next((i for i, s in enumerate(segs) if s.id == req.from_segment_id), 0)
        segs = segs[start:]

    results = []
    for seg in segs:
        try:
            result = voices.synthesize_segment(req.book_id, seg, mapping, speed=req.speed)
            results.append(result.model_dump())
        except VoiceSetupError as exc:
            raise HTTPException(
                503,
                str(exc),
            ) from exc
        except Exception as exc:
            raise HTTPException(500, f"TTS failed for segment {seg.id}: {exc}") from exc
    return {"segments": results, "count": len(results)}


@router.get("/audio/{book_id}/{filename}")
def get_audio(book_id: str, filename: str):
    path = config.AUDIO_DIR / book_id / Path(filename).name
    if not path.exists():
        raise HTTPException(404, "Audio not found")
    return FileResponse(path, media_type="audio/wav", filename=path.name)
