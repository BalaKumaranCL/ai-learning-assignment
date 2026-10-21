"""Hunt one planted bad answer in a log file, from the vague complaint only.

    python run_w11_hunt.py                         # schema-v1 logs, scan-based hunt
    python run_w11_hunt.py --indexed data/w11_prod_logs_v2.jsonl

Uses ONLY what the complaint gave: the window "last week" (2026-10-12 to
2026-10-18) and "a deprecated method in a generated sample". It never reads
a trace id, user or package version. Prints each step with line counts and
milliseconds, then the winning trace's id.

The clock here is the script's own (time.perf_counter). A human with a
stopwatch is a separate measurement -- see drill.md.
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))

import w11_hunt as H  # noqa: E402
import w11_logs as L  # noqa: E402

WINDOW = (datetime(2026, 10, 12), datetime(2026, 10, 19))  # "last week": Mon 12th .. Sun 18th


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log", nargs="?", default=os.path.join(BASE, "data", "w11_prod_logs.jsonl"))
    ap.add_argument("--indexed", action="store_true", help="use the schema-v2 output_flags field")
    ap.add_argument("--save", help="write the full hunt record to this json file")
    a = ap.parse_args()

    t0 = time.perf_counter()
    lines = L.read_logs(a.log)
    load_ms = (time.perf_counter() - t0) * 1000

    result = (H.hunt_indexed if a.indexed else H.hunt_v1)(lines, WINDOW)
    wrong_leads = H.input_only_search(lines, WINDOW)

    print(f"log file: {a.log}  ({len(lines)} lines, loaded in {load_ms:.1f} ms)")
    for s in result["steps"]:
        print(f"  {s['step']:<66} {s['in']:>5} -> {s['out']:<4} {s['ms']:>8.2f} ms")
    print(f"hunt time (script clock): {H.fmt_mmss(result['total_ms'] / 1000)}  ({result['total_ms']} ms)")
    print(f"candidates left: {len(result['candidates'])}")
    for c in result["candidates"]:
        print(f"  FOUND {c['trace_id']}  ts={c['ts']}  user={c['user_id']}  app={c['app']}  prompt={c['prompt_version']}")
        print(f"        context ids: {c['retrieved_chunk_ids']}")
    print(f"(for contrast: grepping only the QUESTION for a deprecated name gives {len(wrong_leads)} wrong leads)")

    if a.save:
        rec = {"log": os.path.relpath(a.log, BASE), "lines": len(lines), "steps": result["steps"],
               "total_ms": result["total_ms"], "candidates": [c["trace_id"] for c in result["candidates"]],
               "input_only_wrong_leads": len(wrong_leads)}
        with open(a.save, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(rec, fh, indent=2)


if __name__ == "__main__":
    main()
