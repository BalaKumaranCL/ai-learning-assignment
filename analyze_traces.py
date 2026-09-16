"""Step 1 (replay) and step 2 (seeded 20-sample) of the Week 5 exercise.

Two independent seeds, both separate from the trace-generation seed
(20260915) -- an analyst reading a real production log doesn't control how
the data was produced, only how they sample from it afterward.
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from loader import load_pages  # noqa: E402
from chunkers import StructureAwareChunker, chunk_pages  # noqa: E402
from legacy_v2 import build_legacy_v2_chunks  # noqa: E402
from fusion_retriever import RRFRetriever  # noqa: E402
from tracing import load_traces_jsonl, replay_trace  # noqa: E402
from sampling import seeded_sample  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TRACES_PATH = os.path.join(BASE_DIR, "data", "traces.jsonl")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "w5")

REPLAY_SEED = 501
SAMPLE_SEED = 502
SAMPLE_SIZE = 20

RETRIEVER_VERSION = "rrf_fusion_v1_k60"
GENERATOR_VERSION = "verbatim_cite_or_refuse_v2_rrf_confidence"
MIN_SCORE_THRESHOLD = 0.38


def _build_retriever():
    pages = load_pages(os.path.join(BASE_DIR, "docs"))
    chunks = chunk_pages(pages, StructureAwareChunker())
    combined = chunks + build_legacy_v2_chunks()
    return RRFRetriever(combined)


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    traces = load_traces_jsonl(TRACES_PATH)
    by_id = {t["trace_id"]: t for t in traces}
    all_ids = list(by_id.keys())

    replay_id = seeded_sample(all_ids, 1, REPLAY_SEED)[0]
    sample_ids = seeded_sample(all_ids, SAMPLE_SIZE, SAMPLE_SEED)

    retriever = _build_retriever()
    replay_result = replay_trace(
        by_id[replay_id], retriever, RETRIEVER_VERSION, GENERATOR_VERSION, MIN_SCORE_THRESHOLD
    )

    sample_traces = [by_id[tid] for tid in sample_ids]

    with open(os.path.join(OUTPUT_DIR, "replay_evidence.json"), "w", encoding="utf-8") as fh:
        json.dump({"replay_seed": REPLAY_SEED, "replay_trace_id": replay_id, "result": replay_result}, fh, indent=2)

    with open(os.path.join(OUTPUT_DIR, "sample_20.json"), "w", encoding="utf-8") as fh:
        json.dump({"sample_seed": SAMPLE_SEED, "sample_trace_ids": sample_ids, "traces": sample_traces}, fh, indent=2)

    print("Replay seed:", REPLAY_SEED, "-> trace:", replay_id)
    print("Sample seed:", SAMPLE_SEED, "-> 20 trace_ids:", sample_ids)
    print()
    print("=== REPLAY EVIDENCE ===")
    print(json.dumps(replay_result, indent=2))
    print()
    print("=== SAMPLE 20 TRACES (full content, for manual reading) ===")
    for t in sample_traces:
        print("-" * 100)
        print(json.dumps(t, indent=2))


if __name__ == "__main__":
    main()
