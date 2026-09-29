"""Week 8 Task Set E -- score the docs agent's PATH, not just its answer.

Runs the agent (src/agent_loop.py) over the same 10 migration questions
Week 7 raced (data/w7_questions.json), against the expected tool
trajectories in data/w8_trajectory_expectations.json, and reports:

1. trajectory pass/fail per question, asserted against a SET of accepted
   exact tool-name sequences (more than one entry where a question
   legitimately has more than one valid path -- see that file's "why"
   fields), not one brittle sequence.
2. the four trajectory numbers: tool-choice accuracy, argument validity
   rate, step efficiency, and cost per question (p50 and max, not the mean
   alone).
3. the outcome-vs-trajectory gap (outcome pass rate minus trajectory pass
   rate) and the trace of the named right-answer-wrong-path case.

require_spec_after_deprecation=False (the default) reproduces Week 7's
exact, already-graded agent behavior -- 3 of the 10 questions (Q6/Q8/Q9)
stop after check_deprecation alone because its replacement note happens to
already contain every expected keyword, without ever calling
get_openapi_spec to confirm the current parameter schema. Passing True
applies the Week 8 mitigation (llm_sim.plan_step) and is how
src/failure_zoo.py measures its before/after.
"""

import csv
import json
import os
import statistics

from agent_loop import run_agent
from agent_tools import is_known_name
from scoring import score_answer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "w8")

# The only two tools whose argument is a "fact" (an endpoint/object name)
# that can be checked against real data; search_docs' query is free-text
# natural language, never a fact claim, so it is not scored for validity.
NAME_ARG_BY_TOOL = {"check_deprecation": "name", "get_openapi_spec": "endpoint"}


def load_questions():
    with open(os.path.join(DATA_DIR, "w7_questions.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)["questions"]


def load_expectations():
    with open(os.path.join(DATA_DIR, "w8_trajectory_expectations.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def tool_sequence(result):
    return [c["name"] for c in result["tool_calls"]]


def accepted_tool_set(expectation):
    # The union of tools that appear in ANY accepted sequence -- a call is
    # "wrong tool" only if it falls outside every legitimate path for this
    # question, not merely outside the single shortest one.
    return {tool for seq in expectation["accepted_sequences"] for tool in seq}


def argument_checks(question, result):
    """One bool per name/endpoint argument in this run's tool calls: True
    if it's either a real key in the OpenAPI spec/changelog, or the exact
    entity the question named (a legitimate, deliberately-extracted probe
    that simply has no schema entry -- e.g. asking check_deprecation about
    "Errors" -- is not the same thing as inventing a plausible-sounding
    name nobody asked about, e.g. "Client.sendAsync"). False means fluent
    fiction: an argument that is neither real nor what was asked."""
    checks = []
    for call in result["tool_calls"]:
        arg_name = NAME_ARG_BY_TOOL.get(call["name"])
        if arg_name is None:
            continue
        value = call["arguments"][arg_name]
        grounded = value == question["target_name"] or is_known_name(value, call["arguments"]["api_version"])
        checks.append(grounded)
    return checks


def _evaluate_question(question, expectation, require_spec_after_deprecation):
    result = run_agent(question, require_spec_after_deprecation=require_spec_after_deprecation)
    observed = tool_sequence(result)
    outcome_pass = score_answer(question, result)
    trajectory_pass = observed in expectation["accepted_sequences"]
    allowed = accepted_tool_set(expectation)
    steps_needed = len(expectation["required_tools"])
    steps_taken = len(observed)

    return {
        "id": question["id"],
        "observed_sequence": observed,
        "accepted_sequences": expectation["accepted_sequences"],
        "outcome_pass": outcome_pass,
        "trajectory_pass": trajectory_pass,
        "tool_choice_hits": [t in allowed for t in observed],
        "argument_checks": argument_checks(question, result),
        "steps_taken": steps_taken,
        "steps_needed": steps_needed,
        "step_efficiency": steps_taken / steps_needed if steps_needed else None,
        "missing_tools": sorted(set(expectation["required_tools"]) - set(observed)),
        "total_tokens": result["total_tokens"],
        "total_cost_usd": result["total_cost_usd"],
        "tool_calls": result["tool_calls"],
        "answer": result["answer"],
    }


def run_trajectory_eval(require_spec_after_deprecation=False):
    questions = load_questions()
    expectations = load_expectations()

    rows = [_evaluate_question(q, expectations[q["id"]], require_spec_after_deprecation) for q in questions]
    n = len(rows)

    outcome_pass_rate = sum(r["outcome_pass"] for r in rows) / n
    trajectory_pass_rate = sum(r["trajectory_pass"] for r in rows) / n
    gap = round(outcome_pass_rate - trajectory_pass_rate, 4)

    all_tool_choice_hits = [hit for r in rows for hit in r["tool_choice_hits"]]
    all_arg_checks = [ok for r in rows for ok in r["argument_checks"]]
    costs = [r["total_cost_usd"] for r in rows]
    step_efficiencies = [r["step_efficiency"] for r in rows]

    summary = {
        "outcome_pass_rate": outcome_pass_rate,
        "trajectory_pass_rate": trajectory_pass_rate,
        "outcome_vs_trajectory_gap": gap,
        "tool_choice_accuracy": sum(all_tool_choice_hits) / len(all_tool_choice_hits),
        "argument_validity_rate": sum(all_arg_checks) / len(all_arg_checks) if all_arg_checks else 1.0,
        "step_efficiency_mean": statistics.mean(step_efficiencies),
        "cost_p50_usd": statistics.median(costs),
        "cost_max_usd": max(costs),
    }

    right_answer_wrong_path = [r for r in rows if r["outcome_pass"] and not r["trajectory_pass"]]

    return {
        "rows": rows,
        "summary": summary,
        "right_answer_wrong_path": right_answer_wrong_path,
        "require_spec_after_deprecation": require_spec_after_deprecation,
    }


def _write_results_csv(summary, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "value"])
        writer.writerow(["outcome_pass_rate", f"{summary['outcome_pass_rate']:.2f}"])
        writer.writerow(["trajectory_pass_rate", f"{summary['trajectory_pass_rate']:.2f}"])
        writer.writerow(["outcome_vs_trajectory_gap", f"{summary['outcome_vs_trajectory_gap']:.2f}"])
        writer.writerow(["tool_choice_accuracy", f"{summary['tool_choice_accuracy']:.4f}"])
        writer.writerow(["argument_validity_rate", f"{summary['argument_validity_rate']:.4f}"])
        writer.writerow(["step_efficiency_mean", f"{summary['step_efficiency_mean']:.4f}"])
        writer.writerow(["cost_p50_usd", f"{summary['cost_p50_usd']:.6f}"])
        writer.writerow(["cost_max_usd", f"{summary['cost_max_usd']:.6f}"])


def _write_per_question_csv(rows, path):
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow([
            "id", "outcome_pass", "trajectory_pass", "observed_sequence", "accepted_sequences",
            "steps_taken", "steps_needed", "step_efficiency", "total_tokens", "total_cost_usd",
        ])
        for r in rows:
            writer.writerow([
                r["id"],
                r["outcome_pass"],
                r["trajectory_pass"],
                "|".join(r["observed_sequence"]),
                ";".join("|".join(seq) for seq in r["accepted_sequences"]),
                r["steps_taken"],
                r["steps_needed"],
                f"{r['step_efficiency']:.2f}",
                r["total_tokens"],
                r["total_cost_usd"],
            ])


def write_outputs(eval_result, tag):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    results_path = os.path.join(OUTPUT_DIR, f"trajectory_eval_{tag}.csv")
    per_q_path = os.path.join(OUTPUT_DIR, f"trajectory_eval_{tag}_per_question.csv")
    _write_results_csv(eval_result["summary"], results_path)
    _write_per_question_csv(eval_result["rows"], per_q_path)
    return results_path, per_q_path


if __name__ == "__main__":
    result = run_trajectory_eval(require_spec_after_deprecation=False)
    print(json.dumps(result["summary"], indent=2))
    print(f"\nright-answer-wrong-path cases ({len(result['right_answer_wrong_path'])}):")
    for r in result["right_answer_wrong_path"]:
        print(f"  {r['id']}: called {r['observed_sequence']}, missing {r['missing_tools']}")
    write_outputs(result, "before")
