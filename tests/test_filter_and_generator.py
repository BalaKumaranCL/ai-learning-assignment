import os

from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from retriever import TfidfRetriever
from legacy_v2 import build_legacy_v2_chunks
from generator import answer_question

DOCS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")


def _combined_retriever():
    pages = load_pages(DOCS_DIR)
    structure_chunks = chunk_pages(pages, StructureAwareChunker())
    combined = structure_chunks + build_legacy_v2_chunks()
    return TfidfRetriever(combined)


def test_metadata_filter_narrows_to_requested_sdk_version():
    retriever = _combined_retriever()
    results = retriever.search("retry_backoff_ms default value", top_k=5, sdk_version="v3")
    assert results
    assert all(r.chunk.sdk_version == "v3" for r in results)


def test_metadata_filter_changes_top1_for_the_known_query():
    retriever = _combined_retriever()
    query = "What is the default value of retry_backoff_ms in Client.send?"

    unfiltered = retriever.search(query, top_k=5)
    filtered = retriever.search(query, top_k=5, sdk_version="v3")

    assert unfiltered[0].chunk.sdk_version == "v2"
    assert filtered[0].chunk.sdk_version == "v3"
    assert unfiltered[0].chunk.chunk_id != filtered[0].chunk.chunk_id


def _structure_retriever():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    return TfidfRetriever(chunks)


def test_unanswerable_questions_are_refused():
    retriever = _structure_retriever()
    unanswerable = [
        "What is the rate limit for Client.send()?",
        "How many concurrent requests does the SDK support?",
        "What uptime SLA does the SDK guarantee?",
    ]
    for question in unanswerable:
        result = answer_question(question, retriever)
        assert result["answered"] is False
        assert "can't answer" in result["answer"]


def test_answerable_question_is_answered_with_a_real_citation():
    retriever = _structure_retriever()
    result = answer_question(
        "What is the default value of retry_backoff_ms in Client.send()?", retriever
    )
    assert result["answered"] is True
    assert result["chunk_id"]

    chunk_ids = {c.chunk_id for c in retriever.chunks}
    assert result["chunk_id"] in chunk_ids

    cited_chunk = next(c for c in retriever.chunks if c.chunk_id == result["chunk_id"])
    assert "1000" in cited_chunk.text
    assert "retry_backoff_ms" in cited_chunk.text
