import os

from loader import load_pages
from chunkers import SimpleChunker, StructureAwareChunker, chunk_pages
from models import validate_chunks

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def _client_page(pages):
    return next(p for p in pages if p.page_id == "client")


def test_simple_chunker_produces_chunks():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, SimpleChunker())
    assert len(chunks) > 0


def test_structure_aware_chunker_produces_chunks():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    assert len(chunks) > 0


def test_all_chunks_have_required_metadata():
    pages = load_pages(DOCS_DIR)
    for chunker in (SimpleChunker(), StructureAwareChunker()):
        chunks = chunk_pages(pages, chunker)
        assert validate_chunks(chunks) == []


def test_structure_aware_keeps_parameter_table_intact():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages([_client_page(pages)], StructureAwareChunker())

    params_chunk = next(c for c in chunks if "Parameters" in c.anchor and "Client.send()" in c.anchor)
    assert "| Name | Type | Default | Required |" in params_chunk.text
    assert "| retry_backoff_ms | integer | 1000 | false |" in params_chunk.text
    assert "| timeout_ms | integer | 30000 | false |" in params_chunk.text


def test_structure_aware_keeps_code_fence_intact():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages([_client_page(pages)], StructureAwareChunker())

    example_chunk = next(c for c in chunks if "Example" in c.anchor and "Client.send()" in c.anchor)
    assert example_chunk.text.count("```") == 2
    assert "retry_backoff_ms=2000" in example_chunk.text


def test_simple_chunker_can_split_a_code_fence():
    """The whole point of the naive baseline: given a small enough window,
    it is free to cut a fenced code block in half. A chunk with an odd
    number of ``` markers means the fence opened in one chunk and closed in
    another."""

    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages([_client_page(pages)], SimpleChunker(chunk_size=400, overlap=60))

    split_fence_exists = any(c.text.count("```") % 2 == 1 for c in chunks)
    assert split_fence_exists
