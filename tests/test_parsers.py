from pathlib import Path

from lokalreader.parsers.md import parse_md
from lokalreader.parsers.registry import parse_file
from lokalreader.parsers.txt import parse_txt

ROOT = Path(__file__).resolve().parents[1]
SAMPLES = ROOT / "samples"


def test_parse_txt_chapters():
    doc = parse_txt(SAMPLES / "the_quiet_carriage.txt")
    assert "Quiet" in doc.title or "Carriage" in doc.title
    assert len(doc.chapters) >= 1
    assert any("rain" in ch.text.lower() for ch in doc.chapters)


def test_parse_md_nonfiction():
    doc = parse_md(SAMPLES / "nonfiction_note.md")
    assert "Local" in doc.title or "Speech" in doc.title
    assert len(doc.chapters) >= 1


def test_registry_txt():
    doc = parse_file(SAMPLES / "the_quiet_carriage.txt")
    assert doc.format == "txt"
    assert doc.chapters
