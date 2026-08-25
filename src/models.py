"""Shared data structures used across the pipeline.

A Chunk is the single unit that gets embedded/indexed and retrieved. Every
chunk MUST carry enough metadata to trace it back to the page it came from,
which is what lets us build citations and metadata filters later.
"""

from dataclasses import dataclass, field, asdict

REQUIRED_CHUNK_FIELDS = ("source_file", "page_id", "sdk_version", "page_type")


@dataclass
class Page:
    """One loaded documentation page (frontmatter + raw markdown body)."""

    page_id: str
    sdk_version: str
    page_type: str
    source_file: str
    body: str  # markdown content, frontmatter already stripped


@dataclass
class Chunk:
    """One retrievable piece of text plus its required metadata."""

    chunk_id: str
    text: str
    source_file: str
    page_id: str
    sdk_version: str
    page_type: str
    anchor: str = ""
    strategy: str = ""

    def to_dict(self):
        return asdict(self)


@dataclass
class ScoredChunk:
    """A chunk plus its rank/score within one search result list."""

    rank: int
    score: float
    chunk: Chunk

    def to_dict(self):
        d = {
            "rank": self.rank,
            "score": round(self.score, 4),
            "chunk_id": self.chunk.chunk_id,
            "source_file": self.chunk.source_file,
            "page_id": self.chunk.page_id,
            "sdk_version": self.chunk.sdk_version,
            "page_type": self.chunk.page_type,
            "anchor": self.chunk.anchor,
            "text": self.chunk.text,
        }
        return d


def validate_chunks(chunks):
    """Verify every chunk carries the required metadata fields.

    Returns a list of error strings. An empty list means all chunks passed.
    A chunk missing source_file (or any other required field) is a failed
    ingest per the assignment rules, so this is called right after chunking
    and before anything is indexed.
    """

    errors = []
    for c in chunks:
        for field_name in REQUIRED_CHUNK_FIELDS:
            value = getattr(c, field_name, None)
            if not value:
                errors.append(
                    f"chunk_id={c.chunk_id!r} is missing required metadata field "
                    f"'{field_name}'"
                )
    return errors
