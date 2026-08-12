"""PDF parser using pypdf with form-feed / heading heuristics."""

from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader

from lokalreader.parsers.base import ParsedChapter, ParsedDocument
from lokalreader.parsers.txt import _split_chapters, CHAPTER_RE


def parse_pdf(path: Path) -> ParsedDocument:
    reader = PdfReader(str(path))
    title = path.stem.replace("_", " ").title()
    if reader.metadata and reader.metadata.title:
        title = str(reader.metadata.title).strip() or title

    page_texts: list[str] = []
    for page in reader.pages:
        try:
            page_texts.append(page.extract_text() or "")
        except Exception:
            page_texts.append("")

    # Prefer form-feed style breaks if present; otherwise join and heuristic-split
    joined = "\n\f\n".join(page_texts)
    if "\f" in joined and len(page_texts) > 1:
        chunks = [c.strip() for c in re.split(r"\f+", joined) if c.strip()]
        chapters: list[ParsedChapter] = []
        for i, chunk in enumerate(chunks):
            heading_match = CHAPTER_RE.search(chunk)
            if heading_match and heading_match.start() < 80:
                ch_title = heading_match.group(0).strip()
                body = chunk[heading_match.end() :].strip() or chunk
            else:
                first = chunk.splitlines()[0].strip() if chunk.splitlines() else f"Page {i + 1}"
                ch_title = first[:80] if len(first) < 80 else f"Section {i + 1}"
                body = chunk
            chapters.append(ParsedChapter(title=ch_title, text=body))
        return ParsedDocument(title=title, chapters=chapters, format="pdf")

    full = "\n\n".join(t.strip() for t in page_texts if t.strip())
    return ParsedDocument(title=title, chapters=_split_chapters(full, title), format="pdf")
