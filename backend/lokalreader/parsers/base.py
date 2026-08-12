"""Parser result types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ParsedChapter:
    title: str
    text: str


@dataclass
class ParsedDocument:
    title: str
    chapters: list[ParsedChapter] = field(default_factory=list)
    format: str = "txt"
