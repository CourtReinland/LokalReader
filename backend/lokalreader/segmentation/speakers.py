"""Best-effort narration / dialogue segmentation and speaker labeling."""

from __future__ import annotations

import re
import uuid
from typing import Iterable

from lokalreader.models import Chapter, DocKind, Segment, SegmentKind
from lokalreader.parsers.base import ParsedDocument

# "Hello," said Alice. / Alice said, "Hello."
ATTRIB_AFTER = re.compile(
    r"^[\"“](.+?)[\"”]\s*,?\s*(?:said|asked|replied|whispered|shouted|muttered|answered|cried|exclaimed)\s+([A-Z][\w'-]{1,30})\b",
    re.IGNORECASE | re.DOTALL,
)
ATTRIB_BEFORE = re.compile(
    r"^([A-Z][\w'-]{1,30})\s+(?:said|asked|replied|whispered|shouted|muttered|answered|cried|exclaimed)\s*,?\s*[\"“](.+?)[\"”]",
    re.IGNORECASE | re.DOTALL,
)
# Alice: "Hello" or ALICE: Hello
COLON_SPEAKER = re.compile(
    r"^([A-Z][\w'-]{1,30})\s*:\s*[\"“]?(.*?)[\"”]?\s*$",
    re.DOTALL,
)
QUOTE_BLOCK = re.compile(r"[\"“]([^\"”]+)[\"”]")
NARRATOR = "Narrator"


def _sid() -> str:
    return uuid.uuid4().hex[:12]


def build_chapters(doc: ParsedDocument) -> list[Chapter]:
    chapters: list[Chapter] = []
    for i, ch in enumerate(doc.chapters):
        chapters.append(
            Chapter(
                id=f"ch-{i + 1:03d}",
                title=ch.title or f"Chapter {i + 1}",
                order=i,
                text=ch.text.strip(),
            )
        )
    return chapters


def segment_document(doc: ParsedDocument, kind: DocKind, chapters: list[Chapter]) -> list[Segment]:
    if kind != DocKind.fiction:
        return _segment_nonfiction(chapters)
    return _segment_fiction(chapters)


def _segment_nonfiction(chapters: list[Chapter]) -> list[Segment]:
    segments: list[Segment] = []
    order = 0
    for chapter in chapters:
        for para in _paragraphs(chapter.text):
            for chunk in _chunk_text(para, max_chars=420):
                segments.append(
                    Segment(
                        id=_sid(),
                        chapter_id=chapter.id,
                        order=order,
                        kind=SegmentKind.narration,
                        speaker=NARRATOR,
                        text=chunk,
                    )
                )
                order += 1
    return segments


def _segment_fiction(chapters: list[Chapter]) -> list[Segment]:
    segments: list[Segment] = []
    order = 0
    last_speaker = NARRATOR
    known: list[str] = []
    alt_index = 0
    for chapter in chapters:
        for para in _paragraphs(chapter.text):
            for piece in _split_paragraph(para):
                speaker, kind, text = piece
                if kind == SegmentKind.dialogue:
                    if speaker in {NARRATOR, "Speaker"}:
                        # Alternate among known named characters when attribution is missing
                        if len(known) >= 2:
                            # Prefer the other party vs last named speaker
                            others = [n for n in known if n != last_speaker] or known
                            speaker = others[alt_index % len(others)]
                            alt_index += 1
                        elif known:
                            speaker = known[0]
                        else:
                            speaker = "Speaker"
                    if speaker not in {NARRATOR, "Speaker"} and speaker not in known:
                        known.append(speaker)
                    last_speaker = speaker
                for chunk in _chunk_text(text, max_chars=360):
                    segments.append(
                        Segment(
                            id=_sid(),
                            chapter_id=chapter.id,
                            order=order,
                            kind=kind,
                            speaker=speaker,
                            text=chunk,
                        )
                    )
                    order += 1
    return segments


def _paragraphs(text: str) -> list[str]:
    parts = re.split(r"\n\s*\n", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _split_paragraph(para: str) -> list[tuple[str, SegmentKind, str]]:
    """Return list of (speaker, kind, text) for one paragraph."""
    compact = " ".join(para.split())

    m = ATTRIB_AFTER.match(compact)
    if m:
        dialogue, name = m.group(1).strip(), _clean_name(m.group(2))
        rest = compact[m.end() :].strip(" ,")
        out: list[tuple[str, SegmentKind, str]] = [(name, SegmentKind.dialogue, dialogue)]
        if rest:
            out.append((NARRATOR, SegmentKind.narration, rest))
        return out

    m = ATTRIB_BEFORE.match(compact)
    if m:
        name, dialogue = _clean_name(m.group(1)), m.group(2).strip()
        rest = compact[m.end() :].strip(" ,")
        out = [(name, SegmentKind.dialogue, dialogue)]
        if rest:
            out.append((NARRATOR, SegmentKind.narration, rest))
        return out

    m = COLON_SPEAKER.match(compact)
    if m and len(m.group(1)) <= 24:
        name = _clean_name(m.group(1))
        dialogue = m.group(2).strip() or compact
        return [(name, SegmentKind.dialogue, dialogue)]

    # Mixed quotes inside narration
    quotes = list(QUOTE_BLOCK.finditer(compact))
    if not quotes:
        return [(NARRATOR, SegmentKind.narration, compact)]

    pieces: list[tuple[str, SegmentKind, str]] = []
    cursor = 0
    for q in quotes:
        before = compact[cursor : q.start()].strip(" ,")
        if before:
            # Attribution clinging to quote?
            name = _name_from_attribution(before)
            if name and not pieces:
                # "…," said Name — already handled; treat as narration glue
                pieces.append((NARRATOR, SegmentKind.narration, before))
            else:
                pieces.append((NARRATOR, SegmentKind.narration, before))
        speaker = _nearby_speaker(compact, q.start(), q.end()) or NARRATOR
        pieces.append((speaker if speaker != NARRATOR else "Speaker", SegmentKind.dialogue, q.group(1).strip()))
        cursor = q.end()
    after = compact[cursor:].strip(" ,")
    if after:
        name = _name_from_attribution(after)
        if name and pieces and pieces[-1][1] == SegmentKind.dialogue:
            # Rewrite last dialogue speaker
            spk, kind, text = pieces[-1]
            pieces[-1] = (name, kind, text)
            remainder = ATTRIB_AFTER.sub("", after).strip(" ,")
            # also strip "said Name" patterns
            remainder = re.sub(
                r"^(?:said|asked|replied|whispered|shouted|muttered|answered|cried|exclaimed)\s+[A-Z][\w'-]{1,30}\.?$",
                "",
                after,
                flags=re.IGNORECASE,
            ).strip(" ,")
            if remainder:
                pieces.append((NARRATOR, SegmentKind.narration, remainder))
        else:
            pieces.append((NARRATOR, SegmentKind.narration, after))
    return pieces or [(NARRATOR, SegmentKind.narration, compact)]


def _nearby_speaker(text: str, start: int, end: int) -> str | None:
    window_before = text[max(0, start - 60) : start]
    window_after = text[end : end + 60]
    for window in (window_after, window_before):
        name = _name_from_attribution(window)
        if name:
            return name
    return None


def _name_from_attribution(text: str) -> str | None:
    m = re.search(
        r"(?:said|asked|replied|whispered|shouted|muttered|answered|cried|exclaimed)\s+([A-Z][\w'-]{1,30})",
        text,
        re.IGNORECASE,
    )
    if m:
        return _clean_name(m.group(1))
    m = re.search(
        r"([A-Z][\w'-]{1,30})\s+(?:said|asked|replied|whispered|shouted|muttered|answered|cried|exclaimed)",
        text,
        re.IGNORECASE,
    )
    if m:
        return _clean_name(m.group(1))
    return None


def _clean_name(name: str) -> str:
    name = name.strip().strip(".,:;!?\"'")
    if name.lower() in {"he", "she", "they", "i", "we", "it"}:
        return "Speaker"
    return name[:1].upper() + name[1:]


def _chunk_text(text: str, max_chars: int = 400) -> Iterable[str]:
    text = text.strip()
    if len(text) <= max_chars:
        if text:
            yield text
        return
    # Split on sentence boundaries when possible
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    buf = ""
    for sent in sentences:
        if not sent:
            continue
        if buf and len(buf) + 1 + len(sent) > max_chars:
            yield buf.strip()
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
    if buf.strip():
        yield buf.strip()


def character_names(segments: list[Segment]) -> list[str]:
    names = []
    seen = set()
    for seg in segments:
        if seg.kind == SegmentKind.dialogue and seg.speaker and seg.speaker != NARRATOR:
            key = seg.speaker.lower()
            if key not in seen:
                seen.add(key)
                names.append(seg.speaker)
    return names
