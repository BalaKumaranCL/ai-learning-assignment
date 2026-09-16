import os

from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from legacy_v2 import build_legacy_v2_chunks
from fusion_retriever import RRFRetriever
from tracing import trace_to_dict, write_traces_jsonl, load_traces_jsonl, replay_trace, RICH_SCHEMA_CUTOVER_DAY

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")


def _rich_trace(day):
    return {
        "trace_id": "trace-x",
        "timestamp": "2026-09-10T00:00:00",
        "day": day,
        "question": "What is the default value of retry_backoff_ms in Client.send()?",
        "sdk_version_filter": "v3",
        "answered": True,
        "raw_output": "some text",
        "retriever_version": "rrf_fusion_v1_k60",
        "generator_version": "verbatim_cite_or_refuse_v2_rrf_confidence",
        "min_score_threshold": 0.38,
        "retrieved": [{"rank": 1, "chunk_id": "x", "score": 0.5}],
        "cited_chunk_id": "x",
        "latency_ms": 1.23,
    }


def test_sparse_schema_drops_rich_fields_before_cutover_day():
    trace = _rich_trace(day=RICH_SCHEMA_CUTOVER_DAY - 1)
    persisted = trace_to_dict(trace)

    assert "retrieved" not in persisted
    assert "retriever_version" not in persisted
    assert persisted["question"] == trace["question"]


def test_rich_schema_keeps_all_fields_at_and_after_cutover_day():
    trace = _rich_trace(day=RICH_SCHEMA_CUTOVER_DAY)
    persisted = trace_to_dict(trace)

    assert persisted["retrieved"] == trace["retrieved"]
    assert persisted["retriever_version"] == trace["retriever_version"]


def test_write_and_load_roundtrip(tmp_path):
    traces = [_rich_trace(day=0), _rich_trace(day=6)]
    path = tmp_path / "traces.jsonl"

    write_traces_jsonl(str(path), traces)
    loaded = load_traces_jsonl(str(path))

    assert len(loaded) == 2
    assert "retrieved" not in loaded[0]  # day 0 -> sparse
    assert "retrieved" in loaded[1]  # day 6 -> rich


def test_replay_trace_flags_fields_missing_from_a_sparse_original():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    retriever = RRFRetriever(chunks + build_legacy_v2_chunks())

    sparse_trace = trace_to_dict(_rich_trace(day=0))
    result = replay_trace(sparse_trace, retriever, "rrf_fusion_v1_k60", "verbatim_cite_or_refuse_v2_rrf_confidence", 0.38)

    assert result["trace_id"] == "trace-x"
    assert "retrieved" in result["missing_fields_in_original_trace"]
    assert "retriever_version" in result["missing_fields_in_original_trace"]


def test_replay_trace_reports_no_missing_fields_for_a_rich_original():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    retriever = RRFRetriever(chunks + build_legacy_v2_chunks())

    rich_trace = trace_to_dict(_rich_trace(day=RICH_SCHEMA_CUTOVER_DAY))
    result = replay_trace(rich_trace, retriever, "rrf_fusion_v1_k60", "verbatim_cite_or_refuse_v2_rrf_confidence", 0.38)

    assert result["missing_fields_in_original_trace"] == []
