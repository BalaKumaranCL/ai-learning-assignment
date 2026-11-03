"""Week 12: the MODELLED model-call cost/latency (repo convention, see llm_sim.py).

There is no live LLM anywhere in this repo, so the two places a model would
sit -- the agent's planner (one call per lap) and the answer composer (one
call per request) -- are deterministic stand-ins. Their tokens are estimated
from text length (llm_sim.estimate_tokens) and their dollars/latency come
from the CONSTANTS BELOW, which are assumptions, not billing data. Change a
constant and every cost, latency and 10x number downstream moves with it.

Retrieval, the MCP hop, version resolution, redaction and the code check are
NOT modelled: they are real code, and their latencies are stopwatch readings.
"""

import hashlib

from llm_sim import PRICE_PER_1K_INPUT_USD, PRICE_PER_1K_OUTPUT_USD, estimate_tokens

LLM_BASE_MS = 180.0                 # fixed overhead of one model call
LLM_MS_PER_INPUT_TOKEN = 0.30
LLM_MS_PER_OUTPUT_TOKEN = 9.0
SLOW_PROVIDER_RATE = 0.012          # ~1 call in 83 hits a slow provider response (same constant as Week 11)
SLOW_PROVIDER_MULTIPLIER = 3.5

SYSTEM_PROMPT = (
    "You are the Acme SDK docs assistant. The caller's SDK version has already been resolved: answer for THAT "
    "version only. Use the tools to search the docs, look up a name's lifecycle, and check a name exists; verify "
    "every code sample before you return it. If a method was removed, say it no longer exists and give the "
    "migration. If a name never existed, say so; never invent a signature. Cite every source with its version."
)


def jitter(trace_id, salt):
    return int(hashlib.sha256(f"{trace_id}:{salt}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF


def model_call(trace, name, stage, parent, text_in, text_out, salt):
    """Record one modelled LLM call as a span. -> the span."""
    t_in, t_out = estimate_tokens(text_in), estimate_tokens(text_out)
    ms = (LLM_BASE_MS + LLM_MS_PER_INPUT_TOKEN * t_in + LLM_MS_PER_OUTPUT_TOKEN * t_out) * (0.85 + 0.4 * jitter(trace.trace_id, salt))
    if jitter(trace.trace_id, "slow:" + salt) < SLOW_PROVIDER_RATE:
        ms *= SLOW_PROVIDER_MULTIPLIER
    cost = t_in / 1000 * PRICE_PER_1K_INPUT_USD + t_out / 1000 * PRICE_PER_1K_OUTPUT_USD
    return trace.add(name, stage, parent=parent, latency_ms=ms, tokens_in=t_in, tokens_out=t_out, cost_usd=cost,
                     kind="modelled", model="haiku-class (assumed)")
