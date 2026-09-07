import os

from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from retriever import TfidfRetriever
from fusion_retriever import RRFRetriever
from golden_loader import load_golden_set
from w4_evaluator import evaluate_golden_set, locate_expected_chunk_by_id
from w4_diagnosis import diagnose_question, tally_labels, LABELS

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
GOLDEN_SET_PATH = os.path.join(BASE_DIR, "data", "golden_set.jsonl")


def _chunks():
    pages = load_pages(DOCS_DIR)
    return chunk_pages(pages, StructureAwareChunker())


def _golden_set():
    return load_golden_set(GOLDEN_SET_PATH)


def test_evaluate_golden_set_shape():
    retriever = TfidfRetriever(_chunks())
    result = evaluate_golden_set(_golden_set(), retriever, top_k=3)

    assert result["total"] == 12
    assert 0 <= result["score"] <= 12
    for pq in result["per_question"]:
        assert len(pq["top_3"]) <= 3


def test_locate_expected_chunk_by_id_never_none_for_this_golden_set():
    retriever = TfidfRetriever(_chunks())
    for question in _golden_set():
        result = locate_expected_chunk_by_id(question, retriever)
        assert result is not None, f"{question['id']}'s chunk_id doesn't exist under this retriever at all"


def test_every_diagnosis_label_is_valid_and_tally_sums_to_total():
    retriever = TfidfRetriever(_chunks())
    golden = _golden_set()
    diagnoses = [diagnose_question(q, retriever, top_k=3) for q in golden]

    for d in diagnoses:
        assert d["label"] in LABELS

    tally = tally_labels(diagnoses)
    assert sum(tally.values()) == len(golden)


def test_fused_retriever_scores_at_least_as_well_as_baseline():
    chunks = _chunks()
    golden = _golden_set()
    baseline = TfidfRetriever(chunks)
    fused = RRFRetriever(chunks)

    baseline_score = evaluate_golden_set(golden, baseline, top_k=3)["score"]
    fused_score = evaluate_golden_set(golden, fused, top_k=3)["score"]

    assert fused_score >= baseline_score
