"""Add the two Week-11 cases to the Week-6 suite (data/eval_set.json). Idempotent.

E32  the incident itself, replayed verbatim from the real failed trace: an
     unfiltered caller asks for a code sample and must get a CURRENT sample.
E33  the guard against over-fixing: a caller who explicitly asks for v2 must
     still get the v2 sample. A fix that bans every `sendMessage` would pass
     E32 and quietly break this one.

    python add_w11_eval_cases.py <planted_trace_id>
"""

import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))

import w11_logs as L  # noqa: E402
import w11_service as S  # noqa: E402

EVAL_SET = os.path.join(BASE, "data", "eval_set.json")


def main(trace_id):
    lines = L.read_logs(os.path.join(BASE, "data", "w11_prod_logs.jsonl"))
    bad = next(l for l in lines if l["trace_id"] == trace_id)
    cited = bad["cited_chunk_id"]
    chunk = S.all_chunks()[cited]

    e32 = {
        "id": "E32",
        "question": bad["question"],
        "sdk_version_filter": bad["sdk_version_filter"],
        "answered": bad["answered"],
        "answer": bad["answer"],
        "cited_chunk_id": cited,
        "cited_chunk_sdk_version": chunk.sdk_version,
        "cited_chunk_anchor": chunk.anchor,
        "taxonomy_mode": "stale_deprecated_sample",
        "source": f"w11_incident:{trace_id}",
        "is_regression": True,
        "expect_answered": True,
        "must_contain": ["client.send("],
    }

    q33 = "In SDK v2, show me a code sample of Client.sendMessage"
    t = S.run_request({"ts": "2026-10-21T00:00:00", "user_id": "suite", "app": "suite",
                       "question": q33, "sdk_version_filter": "v2"}, "e33_seed", prompt_version="docs_v1")
    c33 = S.all_chunks()[t["cited_chunk_id"]]
    e33 = {
        "id": "E33",
        "question": q33,
        "sdk_version_filter": "v2",
        "answered": t["answered"],
        "answer": t["answer"],
        "cited_chunk_id": t["cited_chunk_id"],
        "cited_chunk_sdk_version": c33.sdk_version,
        "cited_chunk_anchor": c33.anchor,
        "taxonomy_mode": "correct_complete",
        "source": "w11_guard:v2-legacy-support",
        "is_regression": False,
        "expect_answered": True,
        "must_contain": ["sendMessage"],
    }

    with open(EVAL_SET, "r", encoding="utf-8") as fh:
        cases = json.load(fh)
    cases = [c for c in cases if c["id"] not in ("E32", "E33")] + [e32, e33]
    with open(EVAL_SET, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cases, fh, indent=2)
        fh.write("\n")
    print(f"eval_set.json now has {len(cases)} cases (E32, E33 added)")


if __name__ == "__main__":
    main(sys.argv[1])
