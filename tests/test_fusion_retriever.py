import os

from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from fusion_retriever import RRFRetriever, RRF_K

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")


def _chunks():
    pages = load_pages(DOCS_DIR)
    return chunk_pages(pages, StructureAwareChunker())


def test_search_returns_scored_chunk_shaped_results_with_1_indexed_ranks():
    retriever = RRFRetriever(_chunks())
    results = retriever.search("What is the default retry_backoff_ms if I don't set one on send()?", top_k=5)

    assert len(results) <= 5
    for i, r in enumerate(results, start=1):
        assert r.rank == i


def test_no_rrf_score_exceeds_the_max_possible_two_list_contribution():
    # a chunk can appear at best at rank 1 in BOTH the TF-IDF and BM25 lists,
    # so its RRF score can never exceed 1/(k+1) + 1/(k+1) -- catches an
    # accidental "summed raw scores instead of rank contributions" bug.
    retriever = RRFRetriever(_chunks())
    max_possible = 2 * (1.0 / (RRF_K + 1))

    for question in (
        "What is the default retry_backoff_ms if I don't set one on send()?",
        "How do I know when a stream has finished sending chunks?",
        "My API key got leaked, what steps do I take to rotate it?",
    ):
        results = retriever.search(question, top_k=len(retriever.chunks))
        for r in results:
            assert r.score <= max_possible + 1e-9


def test_rrf_score_matches_manual_computation_for_the_top_result():
    retriever = RRFRetriever(_chunks())
    query = "What is the default retry_backoff_ms if I don't set one on send()?"

    fused_results = retriever.search(query, top_k=1)
    top_chunk_id = fused_results[0].chunk.chunk_id

    tfidf_full = retriever.tfidf.search(query, top_k=len(retriever.chunks))
    bm25_full = retriever.bm25.search(query, top_k=len(retriever.chunks))

    tfidf_rank = next(r.rank for r in tfidf_full if r.chunk.chunk_id == top_chunk_id)
    bm25_rank = next(r.rank for r in bm25_full if r.chunk.chunk_id == top_chunk_id)
    expected_score = 1.0 / (RRF_K + tfidf_rank) + 1.0 / (RRF_K + bm25_rank)

    assert abs(fused_results[0].score - expected_score) < 1e-9


def test_exact_token_golden_question_resolves_correctly_under_fusion():
    retriever = RRFRetriever(_chunks())
    results = retriever.search("Is body_encoding json or form by default in RequestOptions?", top_k=3)

    chunk_ids = [r.chunk.chunk_id for r in results]
    assert "requests::structure::2" in chunk_ids
