"""The stand-in for the LLM that plans tool calls and writes the final
answer. This project has no live model call anywhere (no API key, no SDK in
requirements.txt) -- see judge.py and docs_assistant.py for the same,
already-established pattern of simulating the "AI" piece deterministically
in this from-scratch class exercise instead of spending real API budget on
it. This module plays that role for Week 7: PRICE_PER_1K_*_USD below are a
documented, Haiku-class assumption (not a live billing figure) used only so
token/cost accounting has real numbers to add up and enforce budgets
against; swap in real usage/cost fields from an API response and nothing
else in agent_loop.py or fixed_workflow.py has to change.

compose_answer is the ONE place either system turns gathered tool results
into the final answer text -- the agent's last lap and the workflow's single
end-of-pipeline call both run through it, which is what makes "same output
contract" true rather than asserted.
"""

CHARS_PER_TOKEN = 4  # rough, documented approximation -- not a real tokenizer
PRICE_PER_1K_INPUT_USD = 0.0008
PRICE_PER_1K_OUTPUT_USD = 0.0040

TOOL_PRIORITY = ["check_deprecation", "get_openapi_spec", "search_docs"]

GATHERED_KEY_BY_TOOL = {
    "check_deprecation": "deprecation",
    "get_openapi_spec": "spec",
    "search_docs": "docs",
}


def estimate_tokens(text):
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def compose_answer(question_meta, gathered):
    """Turn whatever tool results have been gathered so far into a single
    answer string. Used both as the literal final answer once the caller
    decides to stop, and (by the agent's planner) as a draft to test
    whether enough has been gathered yet to stop at all."""

    parts = []
    dep = gathered.get("deprecation")
    spec = gathered.get("spec")
    docs = gathered.get("docs")

    if dep is not None:
        if dep["deprecated"]:
            parts.append(
                f"`{dep['name']}` is deprecated in {dep['api_version']}. "
                f"Use `{dep['replacement']}` instead ({dep['note']})."
            )
        else:
            parts.append(f"`{dep['name']}` is not deprecated in {dep['api_version']}.")

    if spec is not None:
        if spec["found"]:
            if spec["parameters"]:
                bits = []
                for p in spec["parameters"]:
                    if p["required"]:
                        bits.append(f"`{p['name']}` ({p['type']}, required)")
                    else:
                        bits.append(f"`{p['name']}` ({p['type']}, default={p['default']!r})")
                parts.append(f"`{spec['endpoint']}` in {spec['api_version']} takes: " + ", ".join(bits) + ".")
            else:
                parts.append(f"`{spec['endpoint']}` in {spec['api_version']} takes no parameters.")
        else:
            parts.append(f"No OpenAPI schema on file for `{spec['endpoint']}` in {spec['api_version']}.")

    if docs is not None:
        if docs["results"]:
            # Quote every retrieved passage, not just the top-ranked one --
            # a real answer-writing model reads its whole context window,
            # and a single-passage summary was silently dropping the actual
            # fact (a table one heading below the top-ranked intro chunk).
            for passage in docs["results"]:
                parts.append(f"Docs ({passage['source_file']} > {passage['anchor']}): {passage['text'].strip()}")
        else:
            parts.append(f"No documentation passages matched {docs['query']!r}.")

    if not parts:
        return "I couldn't find anything on record for this in the docs, the OpenAPI spec, or the changelog."

    return "\n\n".join(parts)


def _next_tool_args(tool_name, question_meta, gathered):
    if tool_name == "check_deprecation":
        return {"name": question_meta["target_name"], "api_version": question_meta["api_version"]}

    if tool_name == "get_openapi_spec":
        dep = gathered.get("deprecation")
        endpoint = dep["lookup_key"] if (dep is not None and dep["deprecated"]) else question_meta["target_name"]
        return {"endpoint": endpoint, "api_version": question_meta["api_version"]}

    if tool_name == "search_docs":
        return {"query": question_meta["question"], "sdk_version": question_meta["api_version"]}

    raise ValueError(f"unknown tool {tool_name!r}")


def plan_step(question_meta, gathered, called_tools, lap_number):
    """One lap of the simulated model's reasoning: think, then either call
    the next tool or answer. Returns (decision, output_text) where
    output_text is what would be the model's completion text for this lap
    (used for output-token accounting).

    question_meta['simulate_thrash']=True models a real agent failure mode:
    a vague, open-ended question with no clear "I'm done" signal, so the
    planner keeps re-querying search_docs with a new follow-up angle every
    lap instead of ever emitting a final answer -- only a budget stops it.
    """

    if question_meta.get("simulate_thrash"):
        query = f"{question_meta['question']} (follow-up check #{lap_number})"
        args = {"query": query, "sdk_version": question_meta["api_version"]}
        return {"type": "tool_call", "tool": "search_docs", "arguments": args}, f"CALL search_docs({args})"

    draft = compose_answer(question_meta, gathered)
    satisfied = all(kw.lower() in draft.lower() for kw in question_meta["expected_keywords"])
    remaining = [t for t in TOOL_PRIORITY if t not in called_tools]

    if satisfied or not remaining:
        return {"type": "final_answer", "answer": draft}, f"FINAL ANSWER: {draft}"

    tool_name = remaining[0]
    args = _next_tool_args(tool_name, question_meta, gathered)
    return {"type": "tool_call", "tool": tool_name, "arguments": args}, f"CALL {tool_name}({args})"
