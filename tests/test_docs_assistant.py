import os

from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from legacy_v2 import build_legacy_v2_chunks
from fusion_retriever import RRFRetriever
from docs_assistant import answer_question

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")


def _retriever():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    combined = chunks + build_legacy_v2_chunks()
    return RRFRetriever(combined)


def test_answers_a_clear_in_corpus_question():
    retriever = _retriever()
    result = answer_question(
        "What is the default value of retry_backoff_ms in Client.send()?", retriever, sdk_version="v3"
    )
    assert result["answered"] is True
    assert result["chunk_id"] is not None


def test_refuses_a_genuinely_out_of_corpus_question():
    retriever = _retriever()
    result = answer_question("What uptime SLA does the SDK guarantee?", retriever, sdk_version="v3")
    assert result["answered"] is False
    assert result["chunk_id"] is None


def test_unfiltered_retry_question_can_surface_the_legacy_v2_chunk():
    # documents the real root cause wired into this week's trace generator:
    # without an sdk_version filter, the legacy v2 answer can outrank v3.
    retriever = _retriever()
    result = answer_question(
        "What is the default value of retry_backoff_ms in Client.send()?", retriever, sdk_version=None
    )
    assert result["answered"] is True
    assert "v2" in result["chunk_id"]


def test_result_shape_matches_generator_answer_question():
    retriever = _retriever()
    result = answer_question("how do I use this SDK", retriever, sdk_version="v3")
    assert set(result.keys()) == {"answered", "answer", "chunk_id", "score"}
