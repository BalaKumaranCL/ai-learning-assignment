import os

from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from golden_loader import load_golden_set, validate_golden_set

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
GOLDEN_SET_PATH = os.path.join(BASE_DIR, "data", "golden_set.jsonl")


def _golden_set():
    return load_golden_set(GOLDEN_SET_PATH)


def test_golden_set_has_exactly_twelve_questions():
    assert len(_golden_set()) == 12


def test_golden_set_passes_validation():
    assert validate_golden_set(_golden_set()) == []


def test_at_least_four_questions_are_exact_token():
    exact_token_count = sum(1 for q in _golden_set() if q["exact_token"] is True)
    assert exact_token_count >= 4


def test_every_golden_chunk_id_exists_in_a_fresh_chunk_build():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    real_chunk_ids = {c.chunk_id for c in chunks}

    for q in _golden_set():
        assert q["chunk_id"] in real_chunk_ids, f"{q['id']} references a chunk_id that no longer exists"


def test_every_question_has_required_fields():
    for q in _golden_set():
        assert q["id"]
        assert q["question"]
        assert q["chunk_id"]
        assert q["source_file"]
        assert isinstance(q["exact_token"], bool)
