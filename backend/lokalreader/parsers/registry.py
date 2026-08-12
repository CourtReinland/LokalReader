"""Dispatch file paths to the right parser."""

from __future__ import annotations

from pathlib import Path

from lokalreader.parsers.base import ParsedDocument
from lokalreader.parsers.docx_parser import parse_docx
from lokalreader.parsers.epub import parse_epub
from lokalreader.parsers.md import parse_md
from lokalreader.parsers.pdf import parse_pdf
from lokalreader.parsers.txt import parse_txt

SUPPORTED = {".txt", ".md", ".markdown", ".pdf", ".epub", ".docx", ".doc"}


def parse_file(path: Path) -> ParsedDocument:
    suffix = path.suffix.lower()
    if suffix in {".txt"}:
        return parse_txt(path)
    if suffix in {".md", ".markdown"}:
        return parse_md(path)
    if suffix == ".pdf":
        return parse_pdf(path)
    if suffix == ".epub":
        return parse_epub(path)
    if suffix in {".docx", ".doc"}:
        if suffix == ".doc":
            raise ValueError("Legacy .doc is not supported; convert to .docx, .txt, or .pdf.")
        return parse_docx(path)
    raise ValueError(f"Unsupported format: {suffix}. Supported: {', '.join(sorted(SUPPORTED))}")
