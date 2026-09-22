"""The identical migration-question task, re-implemented with zero loop:
three hard-coded steps, in the same fixed order, every single time --
check_deprecation, then get_openapi_spec (on whatever check_deprecation
says is the current name), then search_docs -- followed by one model call
that writes the answer from whatever the three steps found.

This is deliberately not "smart": it calls all three tools on every
question, even the ones a reactive agent can answer after just one or two
(see agent_loop.py's early-stop check), because nothing here decides
whether a step is needed -- the code always runs all three.

That get_openapi_spec's argument depends on check_deprecation's result is
NOT the same thing as needing an agent: the STEPS never change (always
these three, always this order), only the VALUE flowing from step 1 into
step 2 does. An agent is for when the steps themselves -- which tools, how
many, in what order -- have to change based on the input; a fixed pipeline
can still pass data between hard-coded steps.
"""

import time

from agent_tools import call_tool
from llm_sim import PRICE_PER_1K_INPUT_USD, PRICE_PER_1K_OUTPUT_USD, compose_answer, estimate_tokens

SYSTEM_PREAMBLE = (
    "You are a docs migration assistant. You have three tools: check_deprecation, "
    "get_openapi_spec, search_docs. Gather only what you need, then answer."
)


def run_workflow(question_meta, sleep_per_step_s=0.01):
    start = time.monotonic()
    tool_calls = []

    # Step 1 -- always check deprecation first.
    dep_args = {"name": question_meta["target_name"], "api_version": question_meta["api_version"]}
    dep = call_tool("check_deprecation", dep_args)
    tool_calls.append({"name": "check_deprecation", "arguments": dep_args})
    if sleep_per_step_s:
        time.sleep(sleep_per_step_s)

    # Step 2 -- schema lookup. The endpoint argument depends on step 1's
    # finding (replacement if deprecated, the originally-named target
    # otherwise), but which STEP runs next never depends on step 1: this
    # call always happens.
    endpoint = dep["lookup_key"] if dep["deprecated"] else question_meta["target_name"]
    spec_args = {"endpoint": endpoint, "api_version": question_meta["api_version"]}
    spec = call_tool("get_openapi_spec", spec_args)
    tool_calls.append({"name": "get_openapi_spec", "arguments": spec_args})
    if sleep_per_step_s:
        time.sleep(sleep_per_step_s)

    # Step 3 -- always confirm/enrich with prose docs too.
    docs_args = {"query": question_meta["question"], "sdk_version": question_meta["api_version"]}
    docs = call_tool("search_docs", docs_args)
    tool_calls.append({"name": "search_docs", "arguments": docs_args})
    if sleep_per_step_s:
        time.sleep(sleep_per_step_s)

    gathered = {"deprecation": dep, "spec": spec, "docs": docs}
    answer = compose_answer(question_meta, gathered)

    input_text = SYSTEM_PREAMBLE + f"\nQ: {question_meta['question']}\n" + str(gathered)
    in_tok = estimate_tokens(input_text)
    out_tok = estimate_tokens(f"FINAL ANSWER: {answer}")
    total_tokens = in_tok + out_tok
    total_cost = (in_tok / 1000) * PRICE_PER_1K_INPUT_USD + (out_tok / 1000) * PRICE_PER_1K_OUTPUT_USD

    return {
        "question_id": question_meta["id"],
        "answer": answer,
        "tool_calls": tool_calls,
        "iterations": 1,
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 6),
        "wall_clock_s": time.monotonic() - start,
        "terminated_by_budget": None,
        "log": [{"step": "fixed-3-step", "in_tokens": in_tok, "out_tokens": out_tok}],
    }
