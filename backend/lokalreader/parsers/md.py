"""Markdown parser — splits on ATX headings."""

from __future__ import annotations

import re
from pathlib import Path

from lokalreader.parsers.base import ParsedChapter, ParsedDocument
from lokalreader.parsers.txt import _split_chapters

HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)


def parse_md(path: Path) -> ParsedDocument:
    raw = path.read_text(encoding="utf-8", errors="replace")
    title = path.stem.replace("_", " ").title()
    matches = list(HEADING_RE.finditer(raw))
    if not matches:
        return ParsedDocument(title=title, chapters=_split_chapters(raw, title), format="md")

    # Prefer h1 as document title
    for match in matches:
        if match.group(1) == "#":
            title = match.group(2).strip()
            break

    chapters: list[ParsedChapter] = []
    # Content before first heading
    if matches[0].start() > 0:
        preface = raw[: matches[0].start()].strip()
        if preface:
            chapters.append(ParsedChapter(title="Preface", text=_strip_md(preface)))

    for i, match in enumerate(matches):
        level = len(match.group(1))
        heading = match.group(2).strip()
        # Skip the document title h1 if it's alone as title
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(raw)
        body = _strip_md(raw[start:end].strip())
        if level == 1 and not body and i == 0:
            continue
        if not body and level == 1:
            continue
        chapters.append(ParsedChapter(title=heading, text=body or heading))

    if not chapters:
        chapters = [ParsedChapter(title=title, text=_strip_md(raw))]
    return ParsedDocument(title=title, chapters=chapters, format="md")


def _strip_md(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_]{1,3}([^*_]+)[*_]{1,3}", r"\1", text)
    text = re.sub(r"^>\s?", "", text, flags=re.MULTILINE)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    return text.strip()
