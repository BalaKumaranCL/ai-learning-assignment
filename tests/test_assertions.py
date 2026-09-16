import os

from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from legacy_v2 import build_legacy_v2_chunks
from assertions import no_unflagged_version_mismatch, code_sample_parses, cited_chunk_exists

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")


def _chunk_by_id():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    combined = chunks + build_legacy_v2_chunks()
    return {c.chunk_id: c for c in combined}


def test_version_mismatch_flags_v2_cited_for_explicit_v3_request():
    chunk_by_id = _chunk_by_id()
    case = {"cited_chunk_id": "client_v2::legacy::0", "sdk_version_filter": "v3"}
    passed, detail = no_unflagged_version_mismatch(case, chunk_by_id)
    assert passed is False


def test_version_mismatch_flags_v2_cited_with_no_filter_requested():
    # the real bug this assertion was fixed for: no filter at all, but a
    # v2 chunk still got cited -- must fail, not be silently skipped.
    chunk_by_id = _chunk_by_id()
    case = {"cited_chunk_id": "client_v2::legacy::0", "sdk_version_filter": None}
    passed, detail = no_unflagged_version_mismatch(case, chunk_by_id)
    assert passed is False


def test_version_mismatch_passes_a_correct_v3_citation():
    chunk_by_id = _chunk_by_id()
    case = {"cited_chunk_id": "client::structure::2", "sdk_version_filter": "v3"}
    passed, detail = no_unflagged_version_mismatch(case, chunk_by_id)
    assert passed is True


def test_version_mismatch_passes_no_citation_at_all():
    chunk_by_id = _chunk_by_id()
    case = {"cited_chunk_id": None, "sdk_version_filter": "v3"}
    passed, detail = no_unflagged_version_mismatch(case, chunk_by_id)
    assert passed is True


def test_code_sample_parses_accepts_valid_python():
    case = {"answer": "### Example\n\n```python\nx = 1\nprint(x)\n```"}
    passed, detail = code_sample_parses(case, {})
    assert passed is True


def test_code_sample_parses_rejects_invalid_python():
    case = {"answer": "```python\ndef broken(:\n```"}
    passed, detail = code_sample_parses(case, {})
    assert passed is False


def test_code_sample_parses_passes_when_no_code_fence_present():
    case = {"answer": "Just a plain sentence, no code here."}
    passed, detail = code_sample_parses(case, {})
    assert passed is True


def test_cited_chunk_exists_true_for_real_chunk():
    chunk_by_id = _chunk_by_id()
    case = {"cited_chunk_id": "client::structure::2"}
    passed, detail = cited_chunk_exists(case, chunk_by_id)
    assert passed is True


def test_cited_chunk_exists_false_for_fake_chunk_id():
    chunk_by_id = _chunk_by_id()
    case = {"cited_chunk_id": "does::not::exist"}
    passed, detail = cited_chunk_exists(case, chunk_by_id)
    assert passed is False
