"""Ties every piece together: load -> chunk -> validate -> retrieve ->
evaluate -> filter demo -> generate -> write output/results.md.

Run this via run.py at the project root, not directly.
"""

import json
import os

from loader import load_pages
from chunkers import SimpleChunker, StructureAwareChunker, chunk_pages
from models import validate_chunks
from retriever import TfidfRetriever
from evaluator import evaluate_strategy, locate_expected_chunk
from generator import answer_question, MIN_SCORE_THRESHOLD
from legacy_v2 import build_legacy_v2_chunks

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")

BONUS_QUERY = "How do you pass a custom retry_backoff_ms value when calling Client.send()?"


def _load_questions():
    with open(os.path.join(DATA_DIR, "questions.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(filename, data):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return path


def run_filter_demo(structure_chunks, questions):
    """Combine the six v3 chunks with the simulated v2 chunks and show that
    filtering on sdk_version changes the top-1 result."""

    legacy_chunks = build_legacy_v2_chunks()
    combined = structure_chunks + legacy_chunks
    retriever = TfidfRetriever(combined)

    query = questions["filter_demo_query"]
    unfiltered = retriever.search(query, top_k=5)
    filtered = retriever.search(query, top_k=5, sdk_version="v3")

    top1_changed = (
        bool(unfiltered)
        and bool(filtered)
        and unfiltered[0].chunk.chunk_id != filtered[0].chunk.chunk_id
    )

    return {
        "query": query,
        "unfiltered": [r.to_dict() for r in unfiltered],
        "filtered": [r.to_dict() for r in filtered],
        "top1_changed": top1_changed,
    }


def run_generation(questions, retriever):
    answerable_ids = set(questions["generation_targets"]["answerable"])
    unanswerable_ids = set(questions["generation_targets"]["unanswerable"])

    answerable_qs = [q for q in questions["answerable"] if q["id"] in answerable_ids]
    unanswerable_qs = [q for q in questions["unanswerable"] if q["id"] in unanswerable_ids]

    answered = []
    for q in answerable_qs:
        result = answer_question(q["question"], retriever)
        result["id"] = q["id"]
        answered.append(result)

    refused = []
    for q in unanswerable_qs:
        result = answer_question(q["question"], retriever)
        result["id"] = q["id"]
        refused.append(result)

    return answered, refused


def run_bonus(simple_retriever, structure_retriever):
    """Try to demonstrate: structure-aware retrieves the parameter row
    tightly, but its answer lacks the code sample, while the naive
    chunker's messier window happens to keep parameter + code together.

    If the two answers don't actually show that contrast, we say so
    honestly instead of writing a result that looks better than reality.
    """

    current_answer = answer_question(BONUS_QUERY, simple_retriever)
    structure_answer = answer_question(BONUS_QUERY, structure_retriever)

    def has_code_usage(result):
        return result["answered"] and "retry_backoff_ms=" in result["answer"]

    demonstrated = has_code_usage(current_answer) and not has_code_usage(structure_answer)

    return {
        "query": BONUS_QUERY,
        "current_answer": current_answer,
        "structure_answer": structure_answer,
        "demonstrated": demonstrated,
    }


def find_retrieval_failure(eval_current, eval_structure, questions, simple_retriever, structure_retriever):
    """Pick the first question that missed under the current chunker and
    look up exactly where its answer really ranked in both strategies, so
    the write-up can explain the true mechanism instead of guessing."""

    by_id = {q["id"]: q for q in questions}

    for cur_q in eval_current["per_question"]:
        if cur_q["hit"]:
            continue
        question = by_id[cur_q["id"]]
        struct_q = next(q for q in eval_structure["per_question"] if q["id"] == cur_q["id"])
        return {
            "id": cur_q["id"],
            "question": cur_q["question"],
            "expected_source_file": cur_q["expected_source_file"],
            "expected_section": cur_q["expected_section"],
            "expected_answer_snippet": cur_q["expected_answer_snippet"],
            "current_hit": cur_q["hit"],
            "current_top5": cur_q["top_5"],
            "current_true_location": locate_expected_chunk(question, simple_retriever),
            "structure_hit": struct_q["hit"],
            "structure_true_location": locate_expected_chunk(question, structure_retriever),
        }
    return None


def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    pages = load_pages(DOCS_DIR)
    assert len(pages) == 6, f"expected exactly 6 v3 pages, found {len(pages)}"

    simple_chunks = chunk_pages(pages, SimpleChunker())
    structure_chunks = chunk_pages(pages, StructureAwareChunker())

    errors = validate_chunks(simple_chunks) + validate_chunks(structure_chunks)
    if errors:
        raise ValueError("chunk metadata validation failed:\n" + "\n".join(errors))

    simple_retriever = TfidfRetriever(simple_chunks)
    structure_retriever = TfidfRetriever(structure_chunks)

    questions = _load_questions()

    eval_current = evaluate_strategy(questions["answerable"], simple_retriever)
    eval_structure = evaluate_strategy(questions["answerable"], structure_retriever)

    filter_demo = run_filter_demo(structure_chunks, questions)

    answered, refused = run_generation(questions, structure_retriever)

    bonus = run_bonus(simple_retriever, structure_retriever)

    failure = find_retrieval_failure(
        eval_current, eval_structure, questions["answerable"], simple_retriever, structure_retriever
    )

    results = {
        "pages": [p.source_file for p in pages],
        "eval_current": eval_current,
        "eval_structure": eval_structure,
        "filter_demo": filter_demo,
        "answered": answered,
        "refused": refused,
        "bonus": bonus,
        "failure": failure,
        "min_score_threshold": MIN_SCORE_THRESHOLD,
    }

    _write_json(
        "chunks.json",
        {
            "current": [c.to_dict() for c in simple_chunks],
            "structure_aware": [c.to_dict() for c in structure_chunks],
        },
    )
    _write_json(
        "search_dump.json",
        {"current": eval_current, "structure_aware": eval_structure},
    )
    _write_json("filter_demo.json", filter_demo)
    _write_json("answers.json", {"answered": answered, "refused": refused, "bonus": bonus})

    from results_md import render_results_md

    md = render_results_md(results, questions)
    results_path = os.path.join(OUTPUT_DIR, "results.md")
    with open(results_path, "w", encoding="utf-8") as fh:
        fh.write(md)

    results["results_path"] = results_path
    return results


if __name__ == "__main__":
    run()
