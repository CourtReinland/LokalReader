"""Heuristic fiction vs nonfiction detection."""

from __future__ import annotations

import re

from lokalreader.models import DocKind
from lokalreader.parsers.base import ParsedDocument

QUOTE_CHARS = "\"“”‘’'«»"
DIALOGUE_LINE_RE = re.compile(
    rf"(?:^|\n)\s*[{re.escape(QUOTE_CHARS)}].+[{re.escape(QUOTE_CHARS)}]",
)
SAID_RE = re.compile(
    r"\b(said|asked|replied|whispered|shouted|muttered|answered|cried|exclaimed)\b",
    re.IGNORECASE,
)
CHAPTER_HINT_RE = re.compile(r"\bchapter\s+\d+\b", re.IGNORECASE)
NONFICTION_HINT_RE = re.compile(
    r"\b(abstract|references|bibliography|doi:|et al\.|figure\s+\d+|table\s+\d+|according to)\b",
    re.IGNORECASE,
)


def detect_kind(doc: ParsedDocument) -> DocKind:
    text = "\n\n".join(ch.text for ch in doc.chapters)
    if not text.strip():
        return DocKind.unknown

    sample = text[:50000]
    words = max(len(sample.split()), 1)
    quote_count = sum(sample.count(c) for c in "\"“”")
    dialogue_lines = len(DIALOGUE_LINE_RE.findall(sample))
    said_hits = len(SAID_RE.findall(sample))
    chapter_hits = len(CHAPTER_HINT_RE.findall(sample))
    nonfiction_hits = len(NONFICTION_HINT_RE.findall(sample))

    quote_density = quote_count / words
    dialogue_density = dialogue_lines / max(sample.count("\n") + 1, 1)

    fiction_score = 0.0
    fiction_score += min(quote_density * 40, 3.0)
    fiction_score += min(dialogue_density * 20, 3.0)
    fiction_score += min(said_hits / 5.0, 2.0)
    fiction_score += min(chapter_hits / 2.0, 1.0)
    fiction_score -= min(nonfiction_hits / 3.0, 3.0)

    if fiction_score >= 2.0:
        return DocKind.fiction
    if fiction_score <= 0.2 and nonfiction_hits >= 2:
        return DocKind.nonfiction
    if quote_density < 0.01 and said_hits == 0:
        return DocKind.nonfiction
    return DocKind.fiction if fiction_score >= 1.0 else DocKind.nonfiction
