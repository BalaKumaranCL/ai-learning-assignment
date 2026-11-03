"""Week 12 capstone -- the ONE entry point.

    python run_w12.py                     everything: the integrated system, the 38-case eval suite, the judge check, the
                                          trajectory eval, the taxonomy re-score, the ablation, the closed loop, the v3.1 drill,
                                          the foreign MCP client, cost and the 10x plan. Writes output/w12/*. ~2 minutes.
    python run_w12.py ask "question" --version 2.4 [--naive]
                                          one question through the integrated engine; prints the answer and its trace
    python run_w12.py demo                Part 1 of the demo: live questions, version resolved before retrieval
    python run_w12.py eval                just the suite + judge check + trajectory
    python run_w12.py loop                just the closed failure -> test -> RED -> fix -> GREEN loop
    python run_w12.py drill31             just the "3.1 ships with two more deprecations" drill
    python run_w12.py reviewer            run the standalone MCP client (reviewer_client.py) against the server

Exit status 0 only if the suite has no unexpected failure AND the judge agrees with the hand labels on >= 85% of answers.
Needs the packages in requirements.txt (scikit-learn, rank_bm25, mcp<2): see README-w12-capstone-e.md.
"""

import argparse
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))
sys.stdout.reconfigure(encoding="utf-8")

try:
    import mcp  # noqa: F401
    import rank_bm25  # noqa: F401
    import sklearn  # noqa: F401
except ImportError as e:   # a stranger's first failure should be one line, not a traceback
    sys.exit(f"Missing package ({e.name}). Fix:  python -m venv .venv  &&  .venv\\Scripts\\pip install -r requirements.txt  &&  .venv\\Scripts\\python run_w12.py")

import w12_costs as COSTS  # noqa: E402
import w12_engine as E  # noqa: E402
import w12_eval as EV  # noqa: E402
import w12_loop as L  # noqa: E402
import w12_report as REP  # noqa: E402
import w12_retrieval_eval as RE  # noqa: E402
import w12_trajectory as T  # noqa: E402
from w12_judge import judge_w12  # noqa: E402

OUT = os.path.join(BASE, "output", "w12")
RUNS = os.path.join(OUT, "runs")
JUDGE_BAR = 0.85

DEMO = [
    ("1. A v2.4 caller asks how to paginate (version resolved first, v2 page cited by version, deprecations surfaced unasked)",
     {"case_id": "demo-paginate", "question": "How do I paginate through my messages?", "sdk_version": "2.4"}),
    ("2. Same caller, plain question: a deprecation nobody asked about",
     {"case_id": "demo-send", "question": "How do I send a message?", "sdk_version": "2.4"}),
    ("3. \"That method no longer exists in 3.0 - here is the migration\"",
     {"case_id": "demo-removed", "question": "Does client.pollStream still work in 3.0?", "sdk_version": "2.4"}),
    ("4. No version anywhere: the engine asks instead of guessing",
     {"case_id": "demo-noversion", "question": "How do I send a message?", "sdk_version": None}),
]


def judge_check(rows):
    with open(os.path.join(BASE, "data", "w12", "hand_labels.json"), "r", encoding="utf-8") as fh:
        labels = {l["id"]: l for l in json.load(fh)["labels"]}
    dis, n = [], 0
    for r in rows:
        if r["category"] == "guard":
            continue
        n += 1
        j = judge_w12({"question": r["question"], "sdk_version_sent": r["result"]["sdk_version_sent"], "answer": r["answer"]})
        if j != labels[r["id"]]["label"]:
            dis.append({"id": r["id"], "judge": j, "label": labels[r["id"]]["label"], "reason": labels[r["id"]]["reason"]})
    return {"n": n, "agree": n - len(dis), "rate": (n - len(dis)) / n, "disagreements": dis}


def show(r, spans=False):
    print(f"\n=== {r['question']}")
    print(f"IDE sent sdk_version={r['sdk_version_sent']!r}  ->  resolved {r['resolution']['version']} via {r['resolution']['source']}  |  trace {r['trace_id']}  |  {r['laps']} laps, "
          f"{len(r['tool_calls'])} tool calls, ${r['totals']['cost_usd']:.5f}, {r['totals']['latency_ms']:.0f} ms (model time modelled)")
    print()
    print(r["answer"])
    if spans:
        print("\n--- spans (one trace id across the agent hop and the MCP hop) ---")
        for s in r["spans"]:
            print(f"  {s['side']:<6} {s['name']:<28} trace={s.get('trace_id') or '(none)':<14} {s['latency_ms']:>8.1f} ms  {s.get('latency_kind', ''):<9} ${s.get('cost_usd', 0):.6f}")


def cmd_ask(a):
    cfg = E.NAIVE if a.naive else E.FIXED
    out, disc = E.run_batch_sync(cfg, [{"case_id": "ask", "question": a.question, "sdk_version": a.version}], run_dir=os.path.join(RUNS, "ask"))
    print(f"config={cfg.name}; MCP tools discovered at runtime: {disc}")
    show(out[0], spans=True)


def cmd_demo():
    out, disc = E.run_batch_sync(E.FIXED, [d[1] for d in DEMO], run_dir=os.path.join(RUNS, "demo"))
    print(f"MCP tools discovered at runtime: {disc}")
    for (title, _), r in zip(DEMO, out):
        print("\n" + "#" * 100 + f"\n{title}")
        show(r)
    print("\nParts 2-4 of the demo (failures found, the number that moved, what's next) come from `python run_w12.py`: see output/w12/demo_script.md")


def cmd_eval():
    fixed = EV.run_suite(E.FIXED, run_dir=os.path.join(RUNS, "fixed"))
    j = judge_check(fixed["rows"])
    t = T.evaluate(fixed["rows"])
    s = fixed["summary"]
    print(f"suite: {s['pass']} pass, {s['fail']} fail, {s['xfail']} xfail of {s['n']}")
    for r in fixed["rows"]:
        print(f"  {r['id']:<4}{r['status']:<6}{r['category']:<20}" + (" | " + " || ".join(f[:110] for f in r["failures"]) if r["failures"] else ""))
    print(f"judge agreement: {j['agree']}/{j['n']} = {100 * j['rate']:.1f}% (bar {100 * JUDGE_BAR:.0f}%)")
    print(f"trajectory: {t['summary']}")
    return s["fail"] == 0 and j["rate"] >= JUDGE_BAR


def cmd_loop():
    r = L.closed_loop()
    print(f"RED   (as shipped, relevance_floor off): {r['red']['summary']['pass']} pass / {r['red']['summary']['fail']} fail   C36: {'; '.join(r['c36_red']['failures'])[:200]}")
    print(f"GREEN (fix on):                          {r['green']['summary']['pass']} pass / {r['green']['summary']['fail']} fail   C36: {r['c36_green']['status']}")
    print(f"fixed: {r['fixed_ids']}   regressions: {r['regressions'] or 'none'}   sweep failing: {len(r['sweep']['failing_before'])} -> {len(r['sweep']['failing_after'])}")
    return not r["regressions"] and not r["green"]["summary"]["fail"]


def cmd_all():
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    R = {}
    print("[1/9] suite on the integrated system (fixed) ...")
    R["fixed"] = EV.run_suite(E.FIXED, run_dir=os.path.join(RUNS, "fixed"))
    print("[2/9] the same suite on the first wiring (naive: every seam fix off) ...")
    R["naive"] = EV.run_suite(E.NAIVE, run_dir=os.path.join(RUNS, "naive"), with_judge=False)
    print("[3/9] judge vs hand labels, trajectory eval, bonus execute-the-check ...")
    R["judge"] = judge_check(R["fixed"]["rows"])
    R["trajectory"] = T.evaluate(R["fixed"]["rows"])
    R["bonus"] = {k: EV.bonus_execute_check(R[k]["rows"]) for k in ("naive", "fixed")}
    print("[4/9] Stack Overflow ablation ...")
    R["retrieval"] = RE.run()
    print("[5/9] closed loop + version sweep ...")
    R["loop"] = L.closed_loop()
    print("[6/9] cost per question and the 10x plan ...")
    results = [r["result"] for r in R["fixed"]["rows"] if r["result"]] + R["loop"]["sweep_results_after"]
    R["tenx"] = COSTS.tenx(results)
    print("[7/9] ablation (18 runs) ...")
    R["ablation"] = L.ablation()
    print("[8/9] v3.1 drill + foreign MCP client ...")
    R["drill"] = L.drill_v31()
    R["foreign"] = L.foreign()
    print("[9/9] demo run, trace example, reports ...")
    demo_out, _ = E.run_batch_sync(E.FIXED, [d[1] for d in DEMO], run_dir=os.path.join(RUNS, "demo"))
    R["demo"] = [(d[0], r) for d, r in zip(DEMO, demo_out)]
    by = lambda cfg, cid: next(r["result"] for r in R[cfg]["rows"] if r["id"] == cid)  # noqa: E731
    R["trace_example"] = {"fixed": by("fixed", "C01"), "naive": by("naive", "C01")}
    REP.write_all(R)

    f, n, j, tr = R["fixed"]["summary"], R["naive"]["summary"], R["judge"], R["trajectory"]["summary"]
    print("\n" + "=" * 92)
    print("WEEK 12 -- SDK Docs Answer Engine: integrated run complete in %.0f s" % (time.time() - t0))
    print("=" * 92)
    print(f"MCP tools discovered at runtime : {R['fixed']['discovery']}")
    print(f"Suite (fixed)                   : {f['pass']} pass, {f['fail']} fail, {f['xfail']} documented-limit XFAIL, of {f['n']} cases")
    print(f"Suite (naive: all seams unfixed): {n['pass']} pass, {n['fail']} fail, {n['xfail']} XFAIL")
    print(f"Wrong-version code samples      : {n['wrong_version_code']}/{n['answers_with_code']} ({100 * n['wrong_version_code_rate']:.1f}%) -> {f['wrong_version_code']}/{f['answers_with_code']} ({100 * f['wrong_version_code_rate']:.1f}%)")
    print(f"Trace broken at the MCP hop     : {n['trace_broken']} -> {f['trace_broken']}      secrets in the server log: {n['canary_leaks']} -> {f['canary_leaks']} of {f['canary_cases']}")
    print(f"Judge vs hand labels            : {j['agree']}/{j['n']} = {100 * j['rate']:.1f}%  (bar {100 * JUDGE_BAR:.0f}%)")
    print(f"Trajectory                      : outcome {100 * tr['outcome_pass_rate']:.0f}% vs trajectory {100 * tr['trajectory_pass_rate']:.0f}%  gap {tr['outcome_vs_trajectory_gap']:.3f}  tool-choice {100 * tr['tool_choice_accuracy']:.1f}%")
    bn, bf = R["bonus"]["naive"], R["bonus"]["fixed"]
    print(f"Bonus (execute-the-check)       : naive: {bn['parses_only']['went_red']} of {bn['parses_only']['passing_with_code']} answers that merely parse go red ({bn['looks_like_code']['went_red']} of {bn['looks_like_code']['passing_with_code']} with the judge, {bn['old_bar']['went_red']} of {bn['old_bar']['passing_with_code']} under the old bar); fixed: {bf['parses_only']['went_red']} of {bf['parses_only']['passing_with_code']}")
    print(f"Closed loop                     : RED {R['loop']['red']['summary']['fail']} fail -> GREEN {R['loop']['green']['summary']['fail']} fail, regressions: {R['loop']['regressions'] or 'none'}")
    print(f"Cost per question               : ${R['tenx']['per_question']['cost_mean']:.5f} (modelled); first limit to break: {R['tenx']['first_to_break']['constraint']} at {R['tenx']['first_to_break']['breaks_at']}x")
    print(f"Foreign MCP client              : {'ran OK' if R['foreign']['ok'] else 'FAILED'} -> output/w12/foreign_client_transcript.md")
    print("\nReports in output/w12/: EVAL_REPORT.md  taxonomy.md  trajectory.md  cost_by_stage.md  tenx.md  ablation.md  closed_loop.md")
    print("                        drill_v31.md  so_ablation.md  bonus_execute_check.md  trace_example.md  demo_run.md  results.json")
    print("Hand-written (not regenerated): seams.md  weaknesses.md  architecture.md  demo_script.md  fresh_eyes.md")
    ok = f["fail"] == 0 and j["rate"] >= JUDGE_BAR and R["foreign"]["ok"]
    print("\nRESULT:", "GREEN" if ok else "RED")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", nargs="?", default="all", choices=["all", "ask", "demo", "eval", "loop", "drill31", "reviewer"])
    ap.add_argument("question", nargs="?")
    ap.add_argument("--version", default=None, help="the SDK version the IDE would send, e.g. 2.4")
    ap.add_argument("--naive", action="store_true", help="run the first wiring (every seam fix off) instead of the integrated system")
    a = ap.parse_args()
    if a.command == "ask":
        if not a.question:
            ap.error("ask needs a question")
        return cmd_ask(a)
    ok = True
    if a.command == "demo":
        return cmd_demo()
    if a.command == "eval":
        ok = cmd_eval()
    elif a.command == "loop":
        ok = cmd_loop()
    elif a.command == "drill31":
        d = L.drill_v31()
        print(json.dumps({k: v for k, v in d.items() if k != "manifest"}, indent=1))
    elif a.command == "reviewer":
        print(L.foreign()["transcript"])
    else:
        ok = cmd_all()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
