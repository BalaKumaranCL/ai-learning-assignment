import json
import os

from loader import load_pages
from chunkers import SimpleChunker, StructureAwareChunker, chunk_pages
from retriever import TfidfRetriever
from evaluator import evaluate_strategy

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
DATA_DIR = os.path.join(BASE_DIR, "data")


def _questions():
    with open(os.path.join(DATA_DIR, "questions.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)["answerable"]


def test_top5_evaluation_returns_a_score_out_of_eight():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    retriever = TfidfRetriever(chunks)

    result = evaluate_strategy(_questions(), retriever)

    assert result["total"] == 8
    assert 0 <= result["score"] <= 8
    assert len(result["per_question"]) == 8
    for q in result["per_question"]:
        assert len(q["top_5"]) <= 5


def test_structure_aware_scores_at_least_as_well_as_current():
    """This is the heart of the assignment: run the SAME 8 questions
    against both strategies and compare real, computed hit counts."""

    pages = load_pages(DOCS_DIR)
    questions = _questions()

    current_chunks = chunk_pages(pages, SimpleChunker())
    structure_chunks = chunk_pages(pages, StructureAwareChunker())

    eval_current = evaluate_strategy(questions, TfidfRetriever(current_chunks))
    eval_structure = evaluate_strategy(questions, TfidfRetriever(structure_chunks))

    assert eval_structure["score"] >= eval_current["score"]
