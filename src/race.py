"""Runs the agent and the fixed workflow over the identical 10 migration
questions and reports the four numbers the tech lead actually asked for:
pass rate, p50 latency, total tokens, cost per question -- for both
systems, so they land in one comparable table."""

import csv
import json
import os
import statistics

from agent_loop import run_agent
from fixed_workflow import run_workflow
from scoring import score_answer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data")
OUTPUT_DIR = os.path.join(BASE_DIR, "output", "w7")


def _load_questions():
    with open(os.path.join(DATA_DIR, "w7_questions.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def _summarize(results, scores):
    n = len(results)
    passed = sum(1 for s in scores if s)
    p50 = statistics.median(r["wall_clock_s"] for r in results)
    total_tokens = sum(r["total_tokens"] for r in results)
    total_cost = sum(r["total_cost_usd"] for r in results)
    return {
        "pass_rate": passed / n,
        "p50_latency_s": p50,
        "total_tokens": total_tokens,
        "cost_per_question_usd": total_cost / n,
    }


def run_race():
    questions = _load_questions()["questions"]

    agent_results, workflow_results = [], []
    agent_scores, workflow_scores = [], []
    per_question_rows = []

    for q in questions:
        a = run_agent(q)
        w = run_workflow(q)
        a_pass = score_answer(q, a)
        w_pass = score_answer(q, w)

        agent_results.append(a)
        workflow_results.append(w)
        agent_scores.append(a_pass)
        workflow_scores.append(w_pass)

        per_question_rows.append({
            "id": q["id"],
            "dependent": q["dependent"],
            "agent_pass": a_pass,
            "agent_tool_calls": len(a["tool_calls"]),
            "agent_tokens": a["total_tokens"],
            "agent_cost_usd": a["total_cost_usd"],
            "agent_latency_s": round(a["wall_clock_s"], 4),
            "workflow_pass": w_pass,
            "workflow_tool_calls": len(w["tool_calls"]),
            "workflow_tokens": w["total_tokens"],
            "workflow_cost_usd": w["total_cost_usd"],
            "workflow_latency_s": round(w["wall_clock_s"], 4),
        })

    agent_summary = _summarize(agent_results, agent_scores)
    workflow_summary = _summarize(workflow_results, workflow_scores)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    race_csv_path = _write_race_csv(agent_summary, workflow_summary)
    per_q_csv_path = _write_per_question_csv(per_question_rows)

    return {
        "agent_summary": agent_summary,
        "workflow_summary": workflow_summary,
        "per_question": per_question_rows,
        "agent_results": agent_results,
        "workflow_results": workflow_results,
        "race_csv_path": race_csv_path,
        "per_question_csv_path": per_q_csv_path,
    }


def _write_race_csv(agent_summary, workflow_summary):
    path = os.path.join(OUTPUT_DIR, "race.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["metric", "agent", "workflow"])
        writer.writerow([
            "pass_rate",
            f"{agent_summary['pass_rate']:.2f}",
            f"{workflow_summary['pass_rate']:.2f}",
        ])
        writer.writerow([
            "p50_latency_s",
            f"{agent_summary['p50_latency_s']:.4f}",
            f"{workflow_summary['p50_latency_s']:.4f}",
        ])
        writer.writerow([
            "total_tokens",
            agent_summary["total_tokens"],
            workflow_summary["total_tokens"],
        ])
        writer.writerow([
            "cost_per_question_usd",
            f"{agent_summary['cost_per_question_usd']:.6f}",
            f"{workflow_summary['cost_per_question_usd']:.6f}",
        ])
    return path


def _write_per_question_csv(rows):
    path = os.path.join(OUTPUT_DIR, "race_per_question.csv")
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


if __name__ == "__main__":
    result = run_race()
    print(json.dumps(result["agent_summary"], indent=2))
    print(json.dumps(result["workflow_summary"], indent=2))
