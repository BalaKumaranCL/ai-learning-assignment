"""Ties the Week 4 experiment together: load -> chunk -> validate ->
baseline retriever -> baseline hit-rate@3 -> diagnose every non-clean-hit ->
build the ONE retrieval change (BM25 + RRF fusion) -> re-measure hit-rate@3
and latency -> compare before/after -> write output/w4/results.md.

Entirely additive: reuses the same docs/, the same shipped
StructureAwareChunker, and the same TfidfRetriever Week 3 already built,
completely untouched. Nothing here modifies Week 3's pipeline, output, or
questions.json.
"""

import json
import os

from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from models import validate_chunks
from retriever import TfidfRetriever
from fusion_retriever import RRFRetriever
from golden_loader import load_golden_set, validate_golden_set
from w4_evaluator import evaluate_golden_set
from w4_diagnosis import diagnose_question, tally_labels, compare_before_after
from latency import time_search_calls, p50_latency_ms

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "w4")

TOP_K = 3


def _write_json(filename, data):
    path = os.path.join(OUTPUT_DIR, filename)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
    return path


def run():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    errors = validate_chunks(chunks)
    if errors:
        raise ValueError("chunk metadata validation failed:\n" + "\n".join(errors))

    golden = load_golden_set(os.path.join(DATA_DIR, "golden_set.jsonl"))
    golden_errors = validate_golden_set(golden)
    if golden_errors:
        raise ValueError("golden set validation failed:\n" + "\n".join(golden_errors))
    questions_by_id = {q["id"]: q for q in golden}

    baseline_retriever = TfidfRetriever(chunks)
    fused_retriever = RRFRetriever(chunks)

    baseline_eval = evaluate_golden_set(golden, baseline_retriever, top_k=TOP_K)
    baseline_diagnoses = [diagnose_question(q, baseline_retriever, top_k=TOP_K) for q in golden]
    tally = tally_labels(baseline_diagnoses)

    fused_eval = evaluate_golden_set(golden, fused_retriever, top_k=TOP_K)
    comparison_rows = compare_before_after(baseline_diagnoses, questions_by_id, fused_retriever, top_k=TOP_K)

    baseline_durations = time_search_calls(baseline_retriever, golden, top_k=TOP_K)
    fused_durations = time_search_calls(fused_retriever, golden, top_k=TOP_K)

    results = {
        "golden_set": golden,
        "baseline_eval": baseline_eval,
        "fused_eval": fused_eval,
        "diagnoses": baseline_diagnoses,
        "tally": tally,
        "comparison_rows": comparison_rows,
        "baseline_p50_ms": p50_latency_ms(baseline_durations),
        "fused_p50_ms": p50_latency_ms(fused_durations),
        "baseline_durations_ms": [d * 1000 for d in baseline_durations],
        "fused_durations_ms": [d * 1000 for d in fused_durations],
    }

    _write_json("baseline_eval.json", baseline_eval)
    _write_json("fused_eval.json", fused_eval)
    _write_json("diagnosis.json", {"diagnoses": baseline_diagnoses, "tally": tally})
    _write_json(
        "latency.json",
        {
            "baseline_p50_ms": results["baseline_p50_ms"],
            "fused_p50_ms": results["fused_p50_ms"],
            "baseline_durations_ms": results["baseline_durations_ms"],
            "fused_durations_ms": results["fused_durations_ms"],
        },
    )
    _write_json("comparison.json", comparison_rows)

    from w4_results_md import render_w4_results_md

    md = render_w4_results_md(results)
    results_path = os.path.join(OUTPUT_DIR, "results.md")
    with open(results_path, "w", encoding="utf-8") as fh:
        fh.write(md)

    results["results_path"] = results_path
    return results


if __name__ == "__main__":
    run()
