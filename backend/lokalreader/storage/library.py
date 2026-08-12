"""On-disk library: books, segments, voice mappings."""

from __future__ import annotations

import json
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from lokalreader import config
from lokalreader.models import BookDocument, BookMeta, Segment, SegmentUpdate, VoiceMapping
from lokalreader.parsers.registry import parse_file
from lokalreader.segmentation.detect import detect_kind
from lokalreader.segmentation.speakers import build_chapters, character_names, segment_document


class Library:
    def __init__(self) -> None:
        config.ensure_dirs()

    def list_books(self) -> list[BookMeta]:
        books = []
        for path in sorted(config.BOOKS_DIR.glob("*/book.json")):
            doc = self._load(path.parent.name)
            if doc:
                books.append(doc.meta)
        return books

    def get(self, book_id: str) -> BookDocument:
        doc = self._load(book_id)
        if not doc:
            raise KeyError(book_id)
        return doc

    def ingest(self, upload_path: Path, original_name: str) -> BookDocument:
        book_id = uuid.uuid4().hex[:10]
        book_dir = config.BOOKS_DIR / book_id
        book_dir.mkdir(parents=True, exist_ok=True)
        dest = book_dir / original_name
        shutil.copy2(upload_path, dest)

        parsed = parse_file(dest)
        kind = detect_kind(parsed)
        chapters = build_chapters(parsed)
        segments = segment_document(parsed, kind, chapters)
        names = character_names(segments)
        meta = BookMeta(
            id=book_id,
            title=parsed.title,
            filename=original_name,
            format=parsed.format,
            kind=kind,
            created_at=datetime.now(timezone.utc).isoformat(),
            chapter_count=len(chapters),
            segment_count=len(segments),
            character_names=names,
        )
        doc = BookDocument(meta=meta, chapters=chapters, segments=segments)
        self._save(doc)
        # Default voice mapping
        mapping = VoiceMapping(book_id=book_id, narrator_voice="", character_voices={})
        self.save_mapping(mapping)
        return doc

    def update_segment(self, book_id: str, segment_id: str, update: SegmentUpdate) -> Segment:
        doc = self.get(book_id)
        for i, seg in enumerate(doc.segments):
            if seg.id == segment_id:
                data = seg.model_dump()
                if update.speaker is not None:
                    data["speaker"] = update.speaker.strip() or "Narrator"
                if update.kind is not None:
                    data["kind"] = update.kind
                if update.text is not None:
                    data["text"] = update.text
                doc.segments[i] = Segment(**data)
                doc.meta.character_names = character_names(doc.segments)
                self._save(doc)
                return doc.segments[i]
        raise KeyError(segment_id)

    def delete(self, book_id: str) -> None:
        book_dir = config.BOOKS_DIR / book_id
        if book_dir.exists():
            shutil.rmtree(book_dir)
        mapping = config.MAPPINGS_DIR / f"{book_id}.json"
        mapping.unlink(missing_ok=True)
        audio_dir = config.AUDIO_DIR / book_id
        if audio_dir.exists():
            shutil.rmtree(audio_dir)

    def get_mapping(self, book_id: str) -> VoiceMapping:
        path = config.MAPPINGS_DIR / f"{book_id}.json"
        if not path.exists():
            return VoiceMapping(book_id=book_id, narrator_voice="", character_voices={})
        return VoiceMapping.model_validate_json(path.read_text(encoding="utf-8"))

    def save_mapping(self, mapping: VoiceMapping) -> VoiceMapping:
        config.MAPPINGS_DIR.mkdir(parents=True, exist_ok=True)
        path = config.MAPPINGS_DIR / f"{mapping.book_id}.json"
        path.write_text(mapping.model_dump_json(indent=2), encoding="utf-8")
        return mapping

    def _save(self, doc: BookDocument) -> None:
        book_dir = config.BOOKS_DIR / doc.meta.id
        book_dir.mkdir(parents=True, exist_ok=True)
        (book_dir / "book.json").write_text(doc.model_dump_json(indent=2), encoding="utf-8")

    def _load(self, book_id: str) -> BookDocument | None:
        path = config.BOOKS_DIR / book_id / "book.json"
        if not path.exists():
            return None
        return BookDocument.model_validate_json(path.read_text(encoding="utf-8"))
