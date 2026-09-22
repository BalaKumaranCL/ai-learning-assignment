"""Entry point: python run_w7.py

Runs the Week 7 Task Set E exercise -- races the hand-built agent against
the fixed workflow over 10 docs-migration questions, then runs the budget
demo -- and writes output/w7/race.csv, output/w7/race_per_question.csv, and
output/w7/budget_termination_log.txt.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from race import run_race  # noqa: E402
from budget_demo import run_budget_demo  # noqa: E402


def main():
    race = run_race()
    agent = race["agent_summary"]
    workflow = race["workflow_summary"]

    print("Week 7 Task Set E -- agent vs fixed workflow, 10 docs-migration questions")
    print(f"{'metric':<22}{'agent':>14}{'workflow':>14}")
    print(f"{'pass_rate':<22}{agent['pass_rate']:>14.2f}{workflow['pass_rate']:>14.2f}")
    print(f"{'p50_latency_s':<22}{agent['p50_latency_s']:>14.4f}{workflow['p50_latency_s']:>14.4f}")
    print(f"{'total_tokens':<22}{agent['total_tokens']:>14}{workflow['total_tokens']:>14}")
    print(f"{'cost_per_question_usd':<22}{agent['cost_per_question_usd']:>14.6f}{workflow['cost_per_question_usd']:>14.6f}")
    print(f"\nrace.csv written to: {race['race_csv_path']}")
    print(f"per-question detail:  {race['per_question_csv_path']}")

    _, budget_log_path = run_budget_demo()
    print(f"\nbudget-termination log written to: {budget_log_path}")


if __name__ == "__main__":
    main()
