import os

from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from bm25_retriever import BM25Retriever, _tokenize
from legacy_v2 import build_legacy_v2_chunks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")


def _chunks():
    pages = load_pages(DOCS_DIR)
    return chunk_pages(pages, StructureAwareChunker())


def test_tokenizer_keeps_underscored_symbols_as_one_token():
    assert "retry_backoff_ms" in _tokenize("What is retry_backoff_ms?")


def test_search_returns_scored_chunk_shaped_results_with_1_indexed_ranks():
    retriever = BM25Retriever(_chunks())
    results = retriever.search("retry_backoff_ms default", top_k=5)

    assert len(results) <= 5
    for i, r in enumerate(results, start=1):
        assert r.rank == i
        assert hasattr(r.chunk, "chunk_id")


def test_exact_token_query_resolves_the_known_chunk_within_top_3():
    retriever = BM25Retriever(_chunks())
    results = retriever.search("What is the default token_refresh_ms for AuthConfig?", top_k=3)

    chunk_ids = [r.chunk.chunk_id for r in results]
    assert "authentication::structure::2" in chunk_ids


def test_sdk_version_filter_narrows_results_like_tfidf_retriever_does():
    combined = _chunks() + build_legacy_v2_chunks()
    retriever = BM25Retriever(combined)

    results = retriever.search("retry_backoff_ms default", top_k=5, sdk_version="v3")
    assert all(r.chunk.sdk_version == "v3" for r in results)
