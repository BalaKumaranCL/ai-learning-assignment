"""Week 10 race: the Week 7 single agent vs the Week 10 docs squad, on the
SAME 10 questions (data/w7_questions.json -- the 10 cases Weeks 7-8 already
use; no new cases written) scored by the SAME judge (scoring.score_answer,
the deterministic keyword check -- no opinion in it, so it cannot favour
either arm).

Reports the four numbers for both arms: pass rate, p50/p99 latency, total
tokens, cost per question. Also the context re-send multiplier and the
largest token share by hand-off.

Latency: the repo's model is simulated, so wall-clock would measure Python,
not a model. Latency here is MODELLED, identically for both arms, from the
calls each arm actually made:
    latency = model_calls * MODEL_CALL_S + tool_calls * TOOL_CALL_S + hops * HOP_S
The three constants are documented assumptions (not measurements), in the
same spirit as llm_sim's price constants; change them and only the latency
rows move -- pass rate, tokens and cost do not depend on them.
"""

import json
import math
import os

from agent_loop import run_agent
from multi_agent import run_squad
from scoring import score_answer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_CALL_S = 1.0   # assumed latency of one LLM call
TOOL_CALL_S = 0.2    # assumed latency of one tool call
HOP_S = 0.05         # assumed latency of one agent-to-agent message


def load_questions():
    with open(os.path.join(BASE_DIR, "data", "w7_questions.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)["questions"]


def percentile(values, p):
    """Nearest-rank percentile (with 10 samples p99 is the max -- stated in the table)."""
    ordered = sorted(values)
    return ordered[max(0, math.ceil(p / 100 * len(ordered)) - 1)]


def latency(model_calls, tool_calls, hops):
    return model_calls * MODEL_CALL_S + tool_calls * TOOL_CALL_S + hops * HOP_S


def run_single(q, flag):
    r = run_agent(q, sleep_per_lap_s=0, require_spec_after_deprecation=flag)
    model_calls = sum(1 for e in r["log"] if "lap" in e)
    return {
        "answer": r["answer"], "total_tokens": r["total_tokens"], "total_cost_usd": r["total_cost_usd"],
        "model_calls": model_calls, "tool_calls": len(r["tool_calls"]), "hops": 0,
        "latency_s": latency(model_calls, len(r["tool_calls"]), 0), "pass": score_answer(q, r),
    }


def run_multi(q, flag, **policy):
    r = run_squad(q, flag=flag, **policy)
    r["latency_s"] = latency(r["model_calls"], r["tool_calls"], r["hops"])
    r["pass"] = score_answer(q, r)
    return r


def summarize(rows):
    n = len(rows)
    lat = [r["latency_s"] for r in rows]
    return {
        "pass_rate": sum(r["pass"] for r in rows) / n,
        "passed": sum(r["pass"] for r in rows),
        "n": n,
        "p50_latency_s": percentile(lat, 50),
        "p99_latency_s": percentile(lat, 99),
        "total_tokens": sum(r["total_tokens"] for r in rows),
        "cost_per_question_usd": sum(r["total_cost_usd"] for r in rows) / n,
        "total_cost_usd": sum(r["total_cost_usd"] for r in rows),
    }


def run_race(flag=False):
    questions = load_questions()
    single = [run_single(q, flag) for q in questions]
    multi = [run_multi(q, flag) for q in questions]
    return {"questions": questions, "single": single, "multi": multi, "single_summary": summarize(single), "multi_summary": summarize(multi)}


def multiplier(race):
    return race["multi_summary"]["total_tokens"] / race["single_summary"]["total_tokens"]


def bucket_shares(race):
    """Token share of every hand-off bucket across the 10 multi-arm questions, largest first."""
    totals = {}
    for r in race["multi"]:
        for bucket, tokens in r["ledger"].bucket_tokens().items():
            totals[bucket] = totals.get(bucket, 0) + tokens
    grand = sum(totals.values())
    return sorted(((b, t, t / grand) for b, t in totals.items()), key=lambda x: -x[1])


def classify_failure(r):
    """One-line label for what the orchestrator actually did, derived from the trace."""
    if r["version_check_ok"] and r["version_attempts"] > 1:
        return "RETRIED and recovered (version check succeeded on a later attempt)"
    if r["version_check_ok"]:
        return "no failure observed"
    if r["disclosed"]:
        return "DEGRADED: retried, then shipped a partial answer that says the version check is missing"
    return "LIED: retried, then shipped an answer with no version check behind it and no disclosure"
