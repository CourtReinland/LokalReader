"""Shared domain models."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocKind(str, Enum):
    fiction = "fiction"
    nonfiction = "nonfiction"
    unknown = "unknown"


class SegmentKind(str, Enum):
    narration = "narration"
    dialogue = "dialogue"


class Chapter(BaseModel):
    id: str
    title: str
    order: int
    text: str


class Segment(BaseModel):
    id: str
    chapter_id: str
    order: int
    kind: SegmentKind
    speaker: str = "Narrator"
    text: str
    editable: bool = True


class BookMeta(BaseModel):
    id: str
    title: str
    filename: str
    format: str
    kind: DocKind = DocKind.unknown
    created_at: str
    chapter_count: int = 0
    segment_count: int = 0
    character_names: list[str] = Field(default_factory=list)


class BookDocument(BaseModel):
    meta: BookMeta
    chapters: list[Chapter]
    segments: list[Segment]


class VoiceInfo(BaseModel):
    id: str
    name: str
    engine: str
    gender: Optional[str] = None
    description: str = ""
    pitch: float = 0.0
    rate: float = 1.0
    rvc_model: Optional[str] = None


class VoiceMapping(BaseModel):
    book_id: str
    narrator_voice: str
    character_voices: dict[str, str] = Field(default_factory=dict)
    speed: float = 1.0
    use_rvc: bool = True


class SegmentUpdate(BaseModel):
    speaker: Optional[str] = None
    kind: Optional[SegmentKind] = None
    text: Optional[str] = None


class PlaybackRequest(BaseModel):
    book_id: str
    segment_ids: Optional[list[str]] = None
    chapter_id: Optional[str] = None
    from_segment_id: Optional[str] = None
    speed: Optional[float] = None
    # Cap how many segments one HTTP call may synthesize (Piper→RVC is heavy).
    # Clients should batch (~4–8). Server clamps to SYNTH_BATCH_MAX.
    limit: Optional[int] = None


class SynthesizeResult(BaseModel):
    segment_id: str
    audio_url: str
    voice_id: str
    cached: bool = False
