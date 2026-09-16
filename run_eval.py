"""One command: runs the full eval (deterministic assertions + the current
judge) over every case in data/eval_set.json and prints pass rate by mode.

PASS = every assertion passes AND the judge says the answer is helpful (Y).
Uses judge_v2 (the current version) -- and reports it plainly when that
still marks a genuinely-correct refusal as "not helpful" for the
correctly_refused_oos mode, rather than quietly special-casing it away.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

import json  # noqa: E402

from loader import load_pages  # noqa: E402
from chunkers import StructureAwareChunker, chunk_pages  # noqa: E402
from legacy_v2 import build_legacy_v2_chunks  # noqa: E402
from fusion_retriever import RRFRetriever  # noqa: E402
from assertions import run_assertions, ASSERTIONS  # noqa: E402
from judge import judge_v2  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
EVAL_SET_PATH = os.path.join(BASE_DIR, "data", "eval_set.json")


def _build_chunk_by_id():
    pages = load_pages(os.path.join(BASE_DIR, "docs"))
    chunks = chunk_pages(pages, StructureAwareChunker())
    combined = chunks + build_legacy_v2_chunks()
    return {c.chunk_id: c for c in combined}


def main():
    with open(EVAL_SET_PATH, "r", encoding="utf-8") as fh:
        cases = json.load(fh)

    chunk_by_id = _build_chunk_by_id()

    by_mode = {}
    regression_results = []
    for case in cases:
        assertion_results = run_assertions(case, chunk_by_id)
        assertions_pass = all(a["passed"] for a in assertion_results)
        judge_verdict = judge_v2(case)
        overall_pass = assertions_pass and judge_verdict == "Y"

        mode = case["taxonomy_mode"]
        by_mode.setdefault(mode, {"pass": 0, "total": 0})
        by_mode[mode]["total"] += 1
        by_mode[mode]["pass"] += overall_pass

        if case["is_regression"]:
            regression_results.append((case["id"], case["source"], overall_pass))

    print(f"Eval set: {len(cases)} cases, {len(ASSERTIONS)} deterministic assertions, 1 judged criterion (judge_v2)")
    print()
    print(f"{'Mode':<38} {'Pass':>6} {'Total':>6} {'Rate':>7}")
    print("-" * 60)
    total_pass = total_n = 0
    for mode, r in sorted(by_mode.items(), key=lambda kv: -kv[1]["total"]):
        rate = 100 * r["pass"] / r["total"]
        print(f"{mode:<38} {r['pass']:>6} {r['total']:>6} {rate:>6.1f}%")
        total_pass += r["pass"]
        total_n += r["total"]
    print("-" * 60)
    print(f"{'TOTAL':<38} {total_pass:>6} {total_n:>6} {100*total_pass/total_n:>6.1f}%")
    print()
    print("Regression cases (replayed verbatim from real failed traces):")
    for case_id, source, passed in regression_results:
        print(f"  {case_id} ({source}): {'PASS' if passed else 'FAIL'}")
    print()
    print(
        "Note: correctly_refused_oos scores 0% here on purpose -- judge_v2 "
        "still marks every refusal 'not helpful' regardless of whether the "
        "refusal was correct. That is a known, documented, still-open gap "
        "(see notes_w6.md), not a bug in this report."
    )


if __name__ == "__main__":
    main()
