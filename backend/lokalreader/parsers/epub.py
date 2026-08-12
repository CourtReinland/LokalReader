"""EPUB parser using ebooklib spine order."""

from __future__ import annotations

import re
from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub, ITEM_DOCUMENT

from lokalreader.parsers.base import ParsedChapter, ParsedDocument


def parse_epub(path: Path) -> ParsedDocument:
    book = epub.read_epub(str(path))
    title = path.stem.replace("_", " ").title()
    meta_title = book.get_metadata("DC", "title")
    if meta_title:
        title = str(meta_title[0][0]).strip() or title

    chapters: list[ParsedChapter] = []
    seen: set[str] = set()

    # Prefer spine order
    for item_id, _linear in book.spine:
        item = book.get_item_with_id(item_id)
        if item is None or item.get_type() != ITEM_DOCUMENT:
            continue
        if item.get_name() in seen:
            continue
        seen.add(item.get_name())
        chapter = _item_to_chapter(item, fallback=f"Section {len(chapters) + 1}")
        if chapter and chapter.text.strip():
            chapters.append(chapter)

    if not chapters:
        for item in book.get_items_of_type(ITEM_DOCUMENT):
            if item.get_name() in seen:
                continue
            chapter = _item_to_chapter(item, fallback=f"Section {len(chapters) + 1}")
            if chapter and chapter.text.strip():
                chapters.append(chapter)

    if not chapters:
        chapters = [ParsedChapter(title=title, text="(No extractable text found in this EPUB.)")]

    return ParsedDocument(title=title, chapters=chapters, format="epub")


def _item_to_chapter(item: epub.EpubItem, fallback: str) -> ParsedChapter | None:
    try:
        html = item.get_content().decode("utf-8", errors="replace")
    except Exception:
        return None
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav"]):
        tag.decompose()
    heading = soup.find(["h1", "h2", "h3", "title"])
    ch_title = heading.get_text(" ", strip=True) if heading else fallback
    if heading:
        heading.decompose()
    text = soup.get_text("\n", strip=True)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return None
    return ParsedChapter(title=ch_title or fallback, text=text)
