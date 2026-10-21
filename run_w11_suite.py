"""The Week-6 eval suite, re-run LIVE against the Week-11 service.

    python run_w11_suite.py                       # active prompt version
    python run_w11_suite.py --prompt docs_v1      # pin one

run_eval.py (Week 6) scores the answers that were STORED in eval_set.json, so
changing a prompt can never change its score. This runner instead sends every
case's question (and its sdk_version_filter) through w11_service.run_request
under the chosen prompt version and scores what comes back -- the only way a
prompt fix can turn a case from RED to GREEN, and the only way a fix can
silently break a neighbour.

A case PASSES when:
  * all 4 deterministic assertions pass (src/assertions.py), AND
  * if the case says how it must be answered, it is: `expect_answered`
    (cases tagged correct_complete must be answered; correctly_refused_oos
    must be refused -- stops "refuse everything" from looking like a fix), AND
  * every string in `must_contain` appears in the answer.
The judged criterion (judge_v2) is NOT part of this gate: Week 6 documents it
as marking every refusal "not helpful", so it cannot separate a good fix from
a bad one. That decision is deliberate and is repeated in the README.

Exit status 1 if any case fails.
"""

import argparse
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))

import w11_service as S  # noqa: E402
from assertions import run_assertions  # noqa: E402

EVAL_SET = os.path.join(BASE, "data", "eval_set.json")
EXPECT_BY_MODE = {"correct_complete": True, "correctly_refused_oos": False}


def run_case(case, chunk_by_id, prompt_version):
    trace = S.run_request(
        {"ts": "2026-10-21T00:00:00", "user_id": "suite", "app": "suite",
         "question": case["question"], "sdk_version_filter": case["sdk_version_filter"]},
        f"suite_{case['id']}", prompt_version=prompt_version)
    live = {"answer": trace["answer"], "answered": trace["answered"], "cited_chunk_id": trace["cited_chunk_id"],
            "sdk_version_filter": case["sdk_version_filter"]}
    failures = [f"{a['name']}: {a['detail']}" for a in run_assertions(live, chunk_by_id) if not a["passed"]]

    expect = case.get("expect_answered", EXPECT_BY_MODE.get(case["taxonomy_mode"]))
    if expect is not None and trace["answered"] != expect:
        failures.append(f"answered_as_expected: expected answered={expect}, got {trace['answered']}")
    for needle in case.get("must_contain", []):
        if needle not in trace["answer"]:
            failures.append(f"must_contain: {needle!r} missing from the answer")
    return {"id": case["id"], "passed": not failures, "failures": failures,
            "cited": trace["cited_chunk_id"], "retrieved": trace["retrieved_chunk_ids"]}


def run_suite(prompt_version):
    with open(EVAL_SET, "r", encoding="utf-8") as fh:
        cases = json.load(fh)
    chunk_by_id = S.all_chunks()
    return [run_case(c, chunk_by_id, prompt_version) for c in cases]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", default=None)
    ap.add_argument("--save", help="write per-case results to this json file")
    a = ap.parse_args()
    pv = a.prompt or S.ACTIVE_PROMPT_VERSION

    results = run_suite(pv)
    passed = sum(r["passed"] for r in results)
    print(f"Week-6 suite, live, prompt_version={pv}, retriever={S.RETRIEVER_VERSION}")
    print(f"{'case':<6}{'result':<8}detail")
    print("-" * 78)
    for r in results:
        print(f"{r['id']:<6}{'PASS' if r['passed'] else 'FAIL':<8}{' | '.join(f.split(':')[0] for f in r['failures'])}")
    print("-" * 78)
    status = "GREEN" if passed == len(results) else "RED"
    print(f"SUITE {status}: {passed}/{len(results)} pass")
    if a.save:
        with open(a.save, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"prompt_version": pv, "passed": passed, "total": len(results), "cases": results}, fh, indent=2)
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
