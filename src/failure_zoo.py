"""Week 8 -- the "zoo": every run classified into exactly one failure mode
(or "clean"), across the 10 real w7 questions plus 4 deliberately-triggered
stress cases (data/w8_zoo_cases.json), one per named failure mode this
week's material calls out that the 10 real questions don't naturally
exercise (loops, wrong tool, made-up inputs, giving up quietly). The 10
real questions contribute a fifth, naturally-occurring mode instead: 3 of
them (Q6/Q8/Q9) stop right after check_deprecation, before ever confirming
the current schema, because its replacement note happens to already
satisfy the crude keyword check -- see trajectory_eval.py and
data/w8_trajectory_expectations.json for the full "why".

run_zoo(require_spec_after_deprecation) runs every case and returns each
run's classification plus per-mode counts; called once before and once
after the Week 8 mitigation to pick the top failure mode and then build the
regression table (requirements 4 and 5 of the task).
"""

import json
import os

from agent_loop import run_agent
from scoring import score_answer
from trajectory_eval import DATA_DIR, argument_checks, load_expectations, load_questions, tool_sequence

MODES = ["loop", "wrong_tool", "hallucinated_argument", "silent_giveup", "premature_stop", "clean", "other_fail"]


def load_zoo_cases():
    with open(os.path.join(DATA_DIR, "w8_zoo_cases.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def classify(question, result, outcome_pass, trajectory_pass, required_tools):
    tool_names = tool_sequence(result)

    if result["terminated_by_budget"] == "max_iterations":
        return "loop"

    if not tool_names:
        return "clean" if outcome_pass else "silent_giveup"

    if not (set(tool_names) & set(required_tools)):
        return "wrong_tool"

    if any(not ok for ok in argument_checks(question, result)):
        return "hallucinated_argument"

    if outcome_pass and not trajectory_pass:
        return "premature_stop"

    if outcome_pass and trajectory_pass:
        return "clean"

    return "other_fail"


def _run_one(question, expectation, require_spec_after_deprecation, source):
    result = run_agent(question, require_spec_after_deprecation=require_spec_after_deprecation)
    observed = tool_sequence(result)
    outcome_pass = score_answer(question, result)
    trajectory_pass = observed in expectation["accepted_sequences"] if expectation is not None else False
    required_tools = expectation["required_tools"] if expectation is not None else question["required_tools"]
    mode = classify(question, result, outcome_pass, trajectory_pass, required_tools)

    return {
        "id": question["id"],
        "source": source,
        "mode": mode,
        "outcome_pass": outcome_pass,
        "trajectory_pass": trajectory_pass,
        "tool_calls": result["tool_calls"],
        "terminated_by_budget": result["terminated_by_budget"],
        "total_tokens": result["total_tokens"],
        "total_cost_usd": result["total_cost_usd"],
    }


def run_zoo(require_spec_after_deprecation=False):
    questions = load_questions()
    expectations = load_expectations()
    zoo_cases = load_zoo_cases()

    runs = [_run_one(q, expectations[q["id"]], require_spec_after_deprecation, "w7_questions") for q in questions]
    runs += [_run_one(c, None, require_spec_after_deprecation, "zoo_synthetic") for c in zoo_cases]

    counts = {m: 0 for m in MODES}
    for r in runs:
        counts[r["mode"]] = counts.get(r["mode"], 0) + 1

    return {"runs": runs, "counts": counts}


def top_failure_mode(counts):
    failure_modes = {m: n for m, n in counts.items() if m not in ("clean",) and n > 0}
    if not failure_modes:
        return None
    return max(failure_modes.items(), key=lambda kv: kv[1])[0]


def regression_table(before_counts, after_counts):
    rows = []
    for mode in MODES:
        before = before_counts.get(mode, 0)
        after = after_counts.get(mode, 0)
        if mode == "clean":
            direction = "n/a"
        elif after > before:
            direction = "WORSE"
        elif after < before:
            direction = "better"
        else:
            direction = "unchanged"
        rows.append({"mode": mode, "before": before, "after": after, "direction": direction})
    return rows


if __name__ == "__main__":
    before = run_zoo(require_spec_after_deprecation=False)
    after = run_zoo(require_spec_after_deprecation=True)
    print("BEFORE counts:", json.dumps(before["counts"], indent=2))
    print("top failure mode (before):", top_failure_mode(before["counts"]))
    print("AFTER counts: ", json.dumps(after["counts"], indent=2))
    print("\nregression table:")
    for row in regression_table(before["counts"], after["counts"]):
        print(f"  {row['mode']:<22} before={row['before']:<3} after={row['after']:<3} {row['direction']}")
