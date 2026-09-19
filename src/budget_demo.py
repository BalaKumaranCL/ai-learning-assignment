"""Demonstrates each of the four enforced budgets firing and terminating
the loop cleanly -- no infinite spin, no crash, just a logged, typed stop.

Uses the DEMO-THRASH question from w7_questions.json: a deliberately
open-ended question with no clear "I'm done" signal (see 'simulate_thrash'
in w7_questions.json and llm_sim.plan_step), which a reactive planner would
otherwise keep circling on forever -- exactly the failure mode budgets
exist to catch. Four separate runs, each with only one budget tight enough
to be the one that actually fires, isolate which check is doing the work.
"""

import json
import os

from agent_loop import run_agent

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "w7")

UNLIMITED = 10**9

TIGHT_BUDGETS = {
    "max_iterations": {"max_iterations": 4, "max_tokens": UNLIMITED, "max_cost_usd": UNLIMITED, "max_wall_clock_s": UNLIMITED},
    "max_tokens": {"max_iterations": UNLIMITED, "max_tokens": 3000, "max_cost_usd": UNLIMITED, "max_wall_clock_s": UNLIMITED},
    "max_cost_usd": {"max_iterations": UNLIMITED, "max_tokens": UNLIMITED, "max_cost_usd": 0.006, "max_wall_clock_s": UNLIMITED},
    "max_wall_clock_s": {"max_iterations": UNLIMITED, "max_tokens": UNLIMITED, "max_cost_usd": UNLIMITED, "max_wall_clock_s": 0.05},
}


def _load_demo_question():
    with open(os.path.join(DATA_DIR, "w7_questions.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)["budget_demo_question"]


def run_budget_demo():
    question = _load_demo_question()
    lines = []
    results = {}

    for budget_name, budgets in TIGHT_BUDGETS.items():
        result = run_agent(question, budgets=budgets, sleep_per_lap_s=0.01)
        results[budget_name] = result
        lines.append(f"=== forcing budget: {budget_name} (budgets={budgets}) ===")
        for entry in result["log"]:
            lines.append(json.dumps(entry))
        lines.append(
            f"RESULT: terminated_by_budget={result['terminated_by_budget']!r} "
            f"iterations={result['iterations']} total_tokens={result['total_tokens']} "
            f"total_cost_usd={result['total_cost_usd']} wall_clock_s={round(result['wall_clock_s'], 4)}"
        )
        lines.append("")
        assert result["terminated_by_budget"] == budget_name, (
            f"expected {budget_name!r} to be the budget that fired, got "
            f"{result['terminated_by_budget']!r} -- another budget is too tight"
        )
        assert result["answer"] is None, "a budget-terminated run must not also return an answer"

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "budget_termination_log.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))

    return results, path


if __name__ == "__main__":
    results, path = run_budget_demo()
    for name, r in results.items():
        print(name, "->", r["terminated_by_budget"])
    print("log written to", path)
