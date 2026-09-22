"""Hand-built ReAct-style agent loop -- no framework. plan -> act -> observe
-> repeat until the model says it's done, or one of four budgets fires.

Every lap resends the whole running transcript to the simulated model (see
llm_sim.py), exactly like a real chat-completions call would, so tokens are
summed lap over lap into total_tokens rather than read off the last call --
that's the "common mistake" this project was warned to avoid, made
impossible by construction here since there is no other place tokens get
counted.
"""

import time

from agent_tools import call_tool
from llm_sim import GATHERED_KEY_BY_TOOL, PRICE_PER_1K_INPUT_USD, PRICE_PER_1K_OUTPUT_USD, estimate_tokens, plan_step

SYSTEM_PREAMBLE = (
    "You are a docs migration assistant. You have three tools: check_deprecation, "
    "get_openapi_spec, search_docs. Gather only what you need, then answer."
)

DEFAULT_BUDGETS = {
    "max_iterations": 6,
    "max_tokens": 20000,
    "max_cost_usd": 0.05,
    "max_wall_clock_s": 10.0,
}


def _history_text(question_meta, transcript):
    lines = [SYSTEM_PREAMBLE, f"Q: {question_meta['question']}"]
    lines.extend(transcript)
    return "\n".join(lines)


def _result(question_meta, answer, tool_calls, iterations, total_tokens, total_cost, start, log, terminated_by_budget):
    return {
        "question_id": question_meta["id"],
        "answer": answer,
        "tool_calls": tool_calls,
        "iterations": iterations,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "wall_clock_s": time.monotonic() - start,
        "terminated_by_budget": terminated_by_budget,
        "log": log,
    }


def run_agent(question_meta, budgets=None, sleep_per_lap_s=0.01):
    budgets = {**DEFAULT_BUDGETS, **(budgets or {})}
    start = time.monotonic()

    transcript = []
    gathered = {}
    called_tools = []
    tool_calls = []
    total_tokens = 0
    total_cost = 0.0
    log = []

    for lap in range(1, budgets["max_iterations"] + 1):
        elapsed = time.monotonic() - start
        if elapsed > budgets["max_wall_clock_s"]:
            log.append({"event": "budget_terminated", "budget": "max_wall_clock_s", "elapsed_s": round(elapsed, 4)})
            return _result(question_meta, None, tool_calls, lap - 1, total_tokens, total_cost, start, log, "max_wall_clock_s")

        decision, output_text = plan_step(question_meta, gathered, called_tools, lap)

        input_text = _history_text(question_meta, transcript)
        in_tok = estimate_tokens(input_text)
        out_tok = estimate_tokens(output_text)
        total_tokens += in_tok + out_tok
        total_cost += (in_tok / 1000) * PRICE_PER_1K_INPUT_USD + (out_tok / 1000) * PRICE_PER_1K_OUTPUT_USD

        log.append({
            "lap": lap,
            "decision": decision,
            "in_tokens": in_tok,
            "out_tokens": out_tok,
            "running_total_tokens": total_tokens,
            "running_total_cost_usd": round(total_cost, 6),
        })

        if total_tokens > budgets["max_tokens"]:
            log.append({"event": "budget_terminated", "budget": "max_tokens", "total_tokens": total_tokens})
            return _result(question_meta, None, tool_calls, lap, total_tokens, total_cost, start, log, "max_tokens")

        if total_cost > budgets["max_cost_usd"]:
            log.append({"event": "budget_terminated", "budget": "max_cost_usd", "total_cost_usd": round(total_cost, 6)})
            return _result(question_meta, None, tool_calls, lap, total_tokens, total_cost, start, log, "max_cost_usd")

        if decision["type"] == "final_answer":
            return _result(question_meta, decision["answer"], tool_calls, lap, total_tokens, total_cost, start, log, None)

        name, args = decision["tool"], decision["arguments"]
        result = call_tool(name, args)
        tool_calls.append({"name": name, "arguments": args})
        called_tools.append(name)
        gathered[GATHERED_KEY_BY_TOOL[name]] = result
        transcript.append(output_text)
        transcript.append(f"OBSERVATION[{name}]: {result}")

        if sleep_per_lap_s:
            time.sleep(sleep_per_lap_s)

    log.append({"event": "budget_terminated", "budget": "max_iterations", "iterations": budgets["max_iterations"]})
    return _result(
        question_meta, None, tool_calls, budgets["max_iterations"], total_tokens, total_cost, start, log, "max_iterations"
    )
