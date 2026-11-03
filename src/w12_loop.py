"""Week 12: the experiments that need MORE THAN ONE run of the suite.

  ablation()      which seam fix removes which failure: each flag ON alone (from NAIVE) and each flag OFF alone (from FIXED)
  closed_loop()   the failure -> test -> RED -> fix -> GREEN loop, with a regression check against the system as it shipped
  drill_v31()     "we ship 3.1 next month with two more deprecations": edit the symbol table, change nothing else, see what goes red
  foreign()       run reviewer_client.py (an MCP client that imports nothing from this repo) against the server
"""

import copy
import json
import os
import subprocess
import sys
import tempfile

import w12_eval as EV
import w12_sweep as SW
from w12_engine import FIXED, NAIVE, run_batch_sync, with_flags

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS = os.path.join(BASE_DIR, "output", "w12", "runs")


def _row(name, out):
    s = out["summary"]
    return {"config": name, "pass": s["pass"], "fail": s["fail"], "xfail": s["xfail"], "n": s["n"],
            "wrong_version_code": f"{s['wrong_version_code']}/{s['answers_with_code']}", "wrong_version_rate": s["wrong_version_code_rate"],
            "trace_broken": s["trace_broken"], "canary_leaks": f"{s['canary_leaks']}/{s['canary_cases']}", "misresolved": s["misresolved"],
            "failing_ids": [r["id"] for r in out["rows"] if r["status"] == "FAIL"]}


def ablation():
    rows = []
    rows.append(_row("naive (all 8 off)", EV.run_suite(NAIVE, run_dir=os.path.join(RUNS, "abl_naive"), with_judge=False)))
    for f in NAIVE.FLAGS:
        cfg = with_flags(NAIVE, f"only_{f}", **{f: True})
        rows.append(_row(f"only {f} ON", EV.run_suite(cfg, run_dir=os.path.join(RUNS, f"abl_only_{f}"), with_judge=False)))
    rows.append(_row("fixed (all 8 on)", EV.run_suite(FIXED, run_dir=os.path.join(RUNS, "abl_fixed"), with_judge=False)))
    for f in FIXED.FLAGS:
        cfg = with_flags(FIXED, f"without_{f}", **{f: False})
        rows.append(_row(f"fixed, {f} OFF", EV.run_suite(cfg, run_dir=os.path.join(RUNS, f"abl_without_{f}"), with_judge=False)))
    return rows


def closed_loop():
    """The failure the version sweep found (a 2.1 caller asking for a header) is guarded by case C36. RED = the system as it shipped
    before the fix (relevance_floor off). GREEN = the fix. Regressions = cases that passed before and fail after."""
    shipped = with_flags(FIXED, "shipped_before_fix", relevance_floor=False)
    red = EV.run_suite(shipped, run_dir=os.path.join(RUNS, "loop_red"))
    green = EV.run_suite(FIXED, run_dir=os.path.join(RUNS, "loop_green"))
    before = {r["id"]: r["status"] for r in red["rows"]}
    after = {r["id"]: r["status"] for r in green["rows"]}
    fixed_ids = [i for i in before if before[i] == "FAIL" and after[i] == "PASS"]
    regressions = [i for i in before if before[i] == "PASS" and after[i] != "PASS"]
    c36_red = next(r for r in red["rows"] if r["id"] == "C36")
    c36_green = next(r for r in green["rows"] if r["id"] == "C36")

    # the sweep: the same 66 requests before and after
    sweep_req = SW.sweep_requests()
    before_sweep, _ = run_batch_sync(shipped, sweep_req, run_dir=os.path.join(RUNS, "sweep_before"))
    after_sweep, _ = run_batch_sync(FIXED, sweep_req, run_dir=os.path.join(RUNS, "sweep_after"))
    bad_before, total = SW.grade(before_sweep)
    bad_after, _ = SW.grade(after_sweep)
    return {"red": red, "green": green, "fixed_ids": fixed_ids, "regressions": regressions, "c36_red": c36_red, "c36_green": c36_green,
            "sweep": {"requests": total, "failing_before": [b["case_id"] for b in bad_before], "failing_after": [b["case_id"] for b in bad_after]},
            "sweep_results_after": after_sweep}


NEW_DEPRECATIONS = [
    {"id": "Client.close", "deprecated": "3.1", "replacement": "Client.shutdown", "replacement_available_since": "3.1"},
    {"id": "RequestOptions.query_params", "deprecated": "3.1", "replacement": "params", "replacement_available_since": "3.1"},
]


def drill_v31():
    """Simulate the 3.1 release landing in the symbol table only (docs, samples and changelog NOT yet updated)."""
    src = os.path.join(BASE_DIR, "corpus", "symbols.json")
    with open(src, "r", encoding="utf-8") as fh:
        raw = json.load(fh)
    raw = copy.deepcopy(raw)
    raw["latest"]["3"] = "3.1"
    for m in raw["members"]:
        if m["id"] == "Client.close":
            m.update(deprecated="3.1", replacement="Client.shutdown", replacement_available_since="3.1")
        if m["id"] == "RequestOptions":
            for p in m["params"]:
                if p["name"] == "query_params":
                    p.update(deprecated="3.1", replacement="params")
            m["params"].append({"name": "params", "introduced": "3.1"})
    raw["members"].append({"id": "Client.shutdown", "kind": "method", "introduced": "3.1", "returns": None, "params": []})
    tmp = os.path.join(tempfile.mkdtemp(prefix="w12_v31_"), "symbols_3_1.json")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, indent=1)

    import w12_index as ix
    import time
    t0 = time.perf_counter()
    ix.ScopedIndex()
    reindex_ms = (time.perf_counter() - t0) * 1000
    old = os.environ.get("W12_MANIFEST")
    os.environ["W12_MANIFEST"] = tmp
    try:
        out = EV.run_suite(FIXED, run_dir=os.path.join(RUNS, "drill_v31"), with_judge=False)
    finally:
        if old is None:
            del os.environ["W12_MANIFEST"]
        else:
            os.environ["W12_MANIFEST"] = old
    red = [r for r in out["rows"] if r["status"] == "FAIL"]
    chunks = ix.load_corpus()
    words = sum(len(c.text.split()) for c in chunks)
    return {"manifest": tmp, "added": NEW_DEPRECATIONS, "red_cases": [{"id": r["id"], "why": r["failures"][0][:200]} for r in red],
            "n": len(out["rows"]), "reindex_ms": round(reindex_ms), "chunks": len(chunks), "words": words,
            "est_embed_tokens": round(words * 1.3)}


def foreign():
    log = os.path.join(BASE_DIR, "output", "w12", "reviewer_server_spans.jsonl")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    open(log, "w").close()                  # the reviewer's server log starts empty every run, so the committed file is reproducible
    p = subprocess.run([sys.executable, os.path.join(BASE_DIR, "reviewer_client.py")], capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=BASE_DIR)
    return {"ok": p.returncode == 0, "transcript": p.stdout, "stderr": p.stderr[-600:]}
