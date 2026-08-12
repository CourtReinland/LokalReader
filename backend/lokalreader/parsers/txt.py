"""Plain-text parser with chapter heuristics."""

from __future__ import annotations

import re
from pathlib import Path

from lokalreader.parsers.base import ParsedChapter, ParsedDocument

CHAPTER_RE = re.compile(
    r"^(?:#{1,3}\s+)?(?:"
    r"chapter\s+[ivxlcdm\d]+"
    r"|part\s+[ivxlcdm\d]+"
    r"|book\s+[ivxlcdm\d]+"
    r"|prologue|epilogue|introduction|foreword|afterword"
    r")\b.*$",
    re.IGNORECASE | re.MULTILINE,
)


def _split_chapters(text: str, fallback_title: str) -> list[ParsedChapter]:
    matches = list(CHAPTER_RE.finditer(text))
    if not matches:
        body = text.strip()
        return [ParsedChapter(title=fallback_title, text=body)] if body else []

    chapters: list[ParsedChapter] = []
    # Leading text before first chapter heading
    if matches[0].start() > 0:
        preface = text[: matches[0].start()].strip()
        if preface:
            chapters.append(ParsedChapter(title="Preface", text=preface))

    for i, match in enumerate(matches):
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        title = match.group(0).strip().lstrip("#").strip()
        if body:
            chapters.append(ParsedChapter(title=title, text=body))
    return chapters or [ParsedChapter(title=fallback_title, text=text.strip())]


def parse_txt(path: Path) -> ParsedDocument:
    raw = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem.replace("_", " ").replace("-", " ").strip().title()
    # First non-empty line as title if it looks short
    for line in raw.splitlines():
        candidate = line.strip().lstrip("#").strip()
        if candidate and len(candidate) < 80:
            title = candidate
            break
    chapters = _split_chapters(raw, title)
    return ParsedDocument(title=title, chapters=chapters, format="txt")
