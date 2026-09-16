"""Two chunking strategies for the same six pages.

SimpleChunker
    A deliberately naive baseline: it just cuts the raw markdown text into
    fixed-size character windows. It has no idea what a header, a table, or
    a code fence is, so it is free to slice a parameter table in half or cut
    a fenced code block into two separate chunks. This is our stand-in for
    "the chunker we already had before this week's work".

StructureAwareChunker
    Splits on markdown headers (## and ###) instead of on a character
    count. While walking the document it tracks whether it is inside a
    fenced code block (```...```) and never treats a '#' inside a fence as a
    header, so a code fence is always kept in one chunk. Because it only
    ever cuts at header boundaries -- never mid-block -- a markdown table
    (header row + separator row + data rows) is also always kept together,
    since a well-formed table can't contain a header line in the middle of
    it.

Both chunkers return a flat list of Chunk objects carrying full metadata.
"""

import re

from models import Chunk

HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")
FENCE_RE = re.compile(r"^```")


def _slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    return text.strip("-")


class SimpleChunker:
    """Fixed-size character windows with optional overlap. No structure."""

    name = "current"

    def __init__(self, chunk_size=400, overlap=60):
        if overlap >= chunk_size:
            raise ValueError("overlap must be smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_page(self, page):
        text = page.body
        chunks = []
        step = self.chunk_size - self.overlap
        start = 0
        index = 0

        while start < len(text):
            end = min(start + self.chunk_size, len(text))
            piece = text[start:end]
            if piece.strip():
                chunks.append(
                    Chunk(
                        chunk_id=f"{page.page_id}::current::{index}",
                        text=piece,
                        source_file=page.source_file,
                        page_id=page.page_id,
                        sdk_version=page.sdk_version,
                        page_type=page.page_type,
                        anchor="",  # the simple chunker has no idea what section this is
                        strategy=self.name,
                    )
                )
                index += 1
            if end == len(text):
                break
            start += step

        return chunks


class StructureAwareChunker:
    """Splits on markdown headers; never splits a table or a code fence."""

    name = "structure_aware"

    # Header levels that start a brand-new chunk. Level 1 (the page title)
    # just updates the breadcrumb and stays attached to the intro text.
    SPLIT_LEVELS = (2, 3)

    def chunk_page(self, page):
        lines = page.body.splitlines()

        chunks = []
        heading_stack = []  # list of heading text, index 0 = h1
        buffer_lines = []
        buffer_anchor = page.page_id
        in_fence = False
        index = 0

        def flush():
            nonlocal buffer_lines, index
            text = "\n".join(buffer_lines).strip()
            if text:
                anchor = " > ".join(heading_stack) if heading_stack else page.page_id
                chunks.append(
                    Chunk(
                        chunk_id=f"{page.page_id}::structure::{index}",
                        text=text,
                        source_file=page.source_file,
                        page_id=page.page_id,
                        sdk_version=page.sdk_version,
                        page_type=page.page_type,
                        anchor=anchor,
                        strategy=StructureAwareChunker.name,
                    )
                )
                index += 1
            buffer_lines = []

        for line in lines:
            if FENCE_RE.match(line):
                in_fence = not in_fence
                buffer_lines.append(line)
                continue

            if not in_fence:
                header_match = HEADER_RE.match(line)
                if header_match:
                    level = len(header_match.group(1))
                    text = header_match.group(2).strip()

                    if level in self.SPLIT_LEVELS:
                        flush()

                    # Update the breadcrumb: keep everything shallower than
                    # this header, then append this header.
                    heading_stack = heading_stack[: level - 1]
                    heading_stack.append(text)

                    buffer_lines.append(line)
                    continue

            buffer_lines.append(line)

        flush()
        return chunks


def chunk_pages(pages, chunker):
    """Run one chunker over every page and return the combined chunk list."""

    all_chunks = []
    for page in pages:
        all_chunks.extend(chunker.chunk_page(page))
    return all_chunks
