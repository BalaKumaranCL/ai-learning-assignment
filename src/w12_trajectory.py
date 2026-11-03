"""Week 8's trajectory eval, on the INTEGRATED agent: score the PATH, not just the answer.

For each trajectory case (a view on an eval case) it compares what the agent did with what a correct agent should do:

  tool-choice accuracy   share of tool calls whose need appears in SOME accepted path for the case (a call is "wrong tool"
                         only if no legitimate path would make it)
  argument validity      every search / lifecycle / exists call carried the right version, and every symbol it named is real
                         or is the one the question named (not fluent fiction)
  path match             the compressed sequence of needs is one of the accepted sequences
  path completeness      EVERY symbol in the emitted code that has a deprecation or removal on record was looked up. An
                         answer can be right because the sample happened to be fine, while the agent never checked
                         what it was about to tell the caller to run
  outcome pass           the eval case passed (assertions + judge)

trajectory pass = path match AND path completeness AND argument validity.
The outcome-vs-trajectory gap = outcome pass rate - trajectory pass rate. A positive gap means right answers reached by an
unsafe path: the "honest number" the brief asks for.
"""

import json
import os

import w12_codecheck as cc
import w12_symbols as sym
import w12_versions as V

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_PATH = os.path.join(BASE_DIR, "data", "w12", "trajectory_cases.json")


def load_cases():
    with open(CASES_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def compress(seq):
    out = []
    for x in seq:
        if not out or out[-1] != x:
            out.append(x)
    return out


def evaluate(suite_rows):
    """suite_rows: the rows of w12_eval.run_suite(...). -> {rows, summary}"""
    by_id = {r["id"]: r for r in suite_rows}
    rows = []
    for t in load_cases():
        r = by_id[t["eval_case"]]
        res = r["result"]
        calls = res["tool_calls"]
        needs = [c["need"] for c in calls]
        observed = compress(needs)
        allowed = {n for seq in t["accepted"] for n in seq}

        choice_hits = [c["need"] in allowed for c in calls]

        # argument validity
        arg_ok, arg_bad = [], []
        scope = res["scope"]
        named = set(res["named"])
        for c in calls:
            a = c.get("args") or {}
            if c["need"] in ("search", "exists", "lifecycle"):
                ok = a.get("sdk_version") is not None
                if c["need"] in ("exists", "lifecycle"):
                    sid = a.get("symbol", "")
                    ok = ok and (sid in named or sym.lifecycle(sid) is not None)
                arg_ok.append(ok)
                if not ok:
                    arg_bad.append(f"{c['need']} {a}")

        # path completeness: symbols with lifecycle events that the emitted code uses must have been looked up
        looked_up = {(c.get("args") or {}).get("symbol") for c in calls if c["need"] == "lifecycle"}
        missing = []
        if res["scope"] and cc.extract_code_blocks(res["answer"]):
            used = cc.check_markdown(res["answer"], res["scope"])["symbols_used"]
            for sid in used:
                rec = sym.lifecycle(sid) or {}
                if (rec.get("deprecated") or rec.get("removed")) and sid not in looked_up:
                    missing.append(sid)

        path_match = observed in t["accepted"]
        complete = not missing
        args_valid = all(arg_ok)
        traj = path_match and complete and args_valid
        rows.append({"id": t["id"], "eval_case": t["eval_case"], "question": r["question"], "observed": observed,
                     "accepted": t["accepted"], "path_match": path_match, "complete": complete, "unchecked_symbols": missing,
                     "args_valid": args_valid, "bad_args": arg_bad, "choice_hits": choice_hits,
                     "outcome_pass": r["status"] in ("PASS",), "trajectory_pass": traj, "n_calls": len(calls),
                     "laps": res["laps"], "trace_id": r["trace_id"], "tokens": res["totals"]["tokens_in"] + res["totals"]["tokens_out"],
                     "cost_usd": res["totals"]["cost_usd"]})
    n = len(rows)
    hits = [h for r in rows for h in r["choice_hits"]]
    outcome = sum(r["outcome_pass"] for r in rows) / n
    traj = sum(r["trajectory_pass"] for r in rows) / n
    summary = {"n": n, "outcome_pass_rate": round(outcome, 4), "trajectory_pass_rate": round(traj, 4),
               "outcome_vs_trajectory_gap": round(outcome - traj, 4),
               "tool_choice_accuracy": round(sum(hits) / len(hits), 4) if hits else None, "tool_calls": len(hits),
               "argument_validity_rate": round(sum(r["args_valid"] for r in rows) / n, 4),
               "path_match_rate": round(sum(r["path_match"] for r in rows) / n, 4),
               "path_completeness_rate": round(sum(r["complete"] for r in rows) / n, 4)}
    wrong_path = [r for r in rows if r["outcome_pass"] and not r["trajectory_pass"]]
    return {"rows": rows, "summary": summary, "right_answer_wrong_path": wrong_path}
