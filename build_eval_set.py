"""Builds data/eval_set.json: 31 cases, each tagged with a Week 5 taxonomy
mode, each answer freshly computed by running the real, unmodified
docs_assistant over the real corpus -- nothing here is hand-typed output.

20 cases are the exact questions from Week 5's seeded random sample
(output/w5/sample_20.json), reusing the mode each was already determined to
be in during Week 5's open coding (see notes.md section 3/4) -- real,
already-validated ground truth, not re-guessed. 11 more cases round out
thin modes: 5 are replayed verbatim from real trace_ids in the full
1200-trace log (2 wrong-version, 3 more over-refusal instances), 6 are
fresh canonical-phrasing questions run live to get clean answered/refused
controls. At least 5 of the 31 are explicit regressions from real failed
traces (only 2 are required).
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from loader import load_pages  # noqa: E402
from chunkers import StructureAwareChunker, chunk_pages  # noqa: E402
from legacy_v2 import build_legacy_v2_chunks  # noqa: E402
from fusion_retriever import RRFRetriever  # noqa: E402
from docs_assistant import answer_question  # noqa: E402
from tracing import load_traces_jsonl  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EVAL_SET_PATH = os.path.join(BASE_DIR, "data", "eval_set.json")

# trace_id -> W5 taxonomy mode, from notes.md section 3/4 (already determined by hand in Week 5)
W5_SAMPLE_MODES = {
    "trace-01035": "wrong_feature_retrieval",
    "trace-00744": "shallow_citation",
    "trace-00345": "over_refusal_no_detail",
    "trace-00720": "correct_complete",
    "trace-00347": "over_refusal_no_detail",
    "trace-00873": "declines_despite_correct_retrieval",
    "trace-00083": "over_refusal_no_detail",
    "trace-00776": "over_refusal_no_detail",
    "trace-01036": "shallow_citation",
    "trace-00159": "over_refusal_no_detail",
    "trace-00505": "correct_complete",
    "trace-00653": "correctly_refused_oos",
    "trace-00403": "over_refusal_no_detail",
    "trace-00221": "correct_complete",
    "trace-00658": "over_refusal_no_detail",
    "trace-01102": "tangential_citation",
    "trace-00478": "correct_complete",
    "trace-00504": "over_refusal_no_detail",
    "trace-01173": "declines_despite_correct_retrieval",
    "trace-00131": "over_refusal_no_detail",
}
W5_REGRESSION_TRACE_IDS = {"trace-01035", "trace-00744", "trace-01102"}  # one per thin/interesting mode

# extra real trace_ids from the full 1200-trace log, not in the W5 sample
EXTRA_TRACE_IDS = {
    "trace-00954": "wrong_version",
    "trace-01128": "wrong_version",
}

# fresh canonical-phrasing questions, run live (not from any trace log)
FRESH_CASES = [
    ("How many requests per second can I make?", "v3", "correctly_refused_oos"),
    ("What is the default region in AuthConfig?", "v3", "over_refusal_no_detail"),
    ("Which fields are required in the Response object?", "v3", "over_refusal_no_detail"),
    ("What does Client.stream() return?", "v3", "over_refusal_no_detail"),
    ("How do I check for errors after calling send()?", "v3", "over_refusal_no_detail"),
    ("What value is passed for retry_backoff_ms in the Client.send() code example?", "v3", "correct_complete"),
    ("Which exception is raised when timeout_ms is exceeded?", "v3", "correct_complete"),
    ("What is the rate limit for Client.send()?", "v3", "correctly_refused_oos"),
    ("What uptime SLA does the SDK guarantee?", "v3", "correctly_refused_oos"),
]


def _build_retriever():
    pages = load_pages(os.path.join(BASE_DIR, "docs"))
    chunks = chunk_pages(pages, StructureAwareChunker())
    combined = chunks + build_legacy_v2_chunks()
    return RRFRetriever(combined)


def _chunk_by_id(retriever):
    return {c.chunk_id: c for c in retriever.chunks}


def _make_case(case_num, question, sdk_version, result, chunk_by_id, mode, source, is_regression):
    cited = chunk_by_id.get(result["chunk_id"]) if result["chunk_id"] else None
    return {
        "id": f"E{case_num:02d}",
        "question": question,
        "sdk_version_filter": sdk_version,
        "answered": result["answered"],
        "answer": result["answer"],
        "cited_chunk_id": result["chunk_id"],
        "cited_chunk_sdk_version": cited.sdk_version if cited else None,
        "cited_chunk_anchor": cited.anchor if cited else None,
        "taxonomy_mode": mode,
        "source": source,
        "is_regression": is_regression,
    }


def build():
    retriever = _build_retriever()
    chunk_by_id = _chunk_by_id(retriever)
    traces_by_id = {t["trace_id"]: t for t in load_traces_jsonl(os.path.join(BASE_DIR, "data", "traces.jsonl"))}

    cases = []
    case_num = 1

    for trace_id, mode in W5_SAMPLE_MODES.items():
        t = traces_by_id[trace_id]
        result = answer_question(t["question"], retriever, sdk_version=t["sdk_version_filter"])
        cases.append(_make_case(
            case_num, t["question"], t["sdk_version_filter"], result, chunk_by_id,
            mode, f"w5_sample:{trace_id}", trace_id in W5_REGRESSION_TRACE_IDS,
        ))
        case_num += 1

    for trace_id, mode in EXTRA_TRACE_IDS.items():
        t = traces_by_id[trace_id]
        result = answer_question(t["question"], retriever, sdk_version=t["sdk_version_filter"])
        cases.append(_make_case(
            case_num, t["question"], t["sdk_version_filter"], result, chunk_by_id,
            mode, f"full_log:{trace_id}", True,
        ))
        case_num += 1

    for question, sdk_version, mode in FRESH_CASES:
        result = answer_question(question, retriever, sdk_version=sdk_version)
        cases.append(_make_case(
            case_num, question, sdk_version, result, chunk_by_id, mode, "fresh", False,
        ))
        case_num += 1

    with open(EVAL_SET_PATH, "w", encoding="utf-8") as fh:
        json.dump(cases, fh, indent=2)

    return cases


if __name__ == "__main__":
    cases = build()
    print(f"Wrote {len(cases)} cases to {EVAL_SET_PATH}")
    modes = {}
    for c in cases:
        modes[c["taxonomy_mode"]] = modes.get(c["taxonomy_mode"], 0) + 1
    for mode, count in sorted(modes.items(), key=lambda x: -x[1]):
        print(f"  {mode}: {count}")
    print(f"  regression cases: {sum(1 for c in cases if c['is_regression'])}")
