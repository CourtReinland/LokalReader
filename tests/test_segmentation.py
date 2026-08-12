from pathlib import Path

from lokalreader.models import DocKind, SegmentKind
from lokalreader.parsers.txt import parse_txt
from lokalreader.parsers.md import parse_md
from lokalreader.segmentation.detect import detect_kind
from lokalreader.segmentation.speakers import build_chapters, character_names, segment_document

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"


def test_detect_fiction():
    doc = parse_txt(SAMPLES / "the_quiet_carriage.txt")
    assert detect_kind(doc) == DocKind.fiction


def test_detect_nonfiction():
    doc = parse_md(SAMPLES / "nonfiction_note.md")
    assert detect_kind(doc) == DocKind.nonfiction


def test_fiction_speakers():
    doc = parse_txt(SAMPLES / "the_quiet_carriage.txt")
    chapters = build_chapters(doc)
    segments = segment_document(doc, DocKind.fiction, chapters)
    assert segments
    dialogue = [s for s in segments if s.kind == SegmentKind.dialogue]
    assert dialogue, "expected dialogue segments"
    names = character_names(segments)
    assert "Mara" in names or "Eli" in names
    # At least two distinct speaking roles when including narrator
    speakers = {s.speaker for s in segments}
    assert len(speakers) >= 2


def test_nonfiction_single_narrator():
    doc = parse_md(SAMPLES / "nonfiction_note.md")
    chapters = build_chapters(doc)
    segments = segment_document(doc, DocKind.nonfiction, chapters)
    assert segments
    assert all(s.speaker == "Narrator" for s in segments)
    assert all(s.kind == SegmentKind.narration for s in segments)
