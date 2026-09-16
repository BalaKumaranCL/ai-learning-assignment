"""Generates a week's worth of synthetic-but-genuinely-computed docs
assistant traces into data/traces.jsonl.

This assignment assumes a live app whose trace file has "grown past a
thousand lines that nobody has read." This practice project has no live
users, so this script plays that week forward: it simulates realistic
traffic (weighted intents, paraphrased the way different developers would
actually ask, spread over 7 days) and runs EVERY one of those questions
through the real, unmodified Week 4 retriever (RRFRetriever) and a
generation wrapper (src/docs_assistant.py -- see its docstring for why this
isn't generator.answer_question() unmodified) -- so every recorded output is
a real, computed result, not a hand-authored fake one.

One deliberate, realistic root cause is wired in: the docs assistant is
called from two integrations. The web widget always passes
sdk_version="v3". The older Slack integration was never updated to pass any
filter at all -- so on Slack, legacy v2 chunks (see legacy_v2.py) compete
unfiltered against the real v3 answer, exactly reproducing the "sometimes
gives outdated code" complaint. Nothing else about the failure modes here
was pre-decided; they are whatever falls out of actually running these
questions through the real pipeline.
"""

import os
import random
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))

from loader import load_pages  # noqa: E402
from chunkers import StructureAwareChunker, chunk_pages  # noqa: E402
from legacy_v2 import build_legacy_v2_chunks  # noqa: E402
from fusion_retriever import RRFRetriever  # noqa: E402
from generator import MIN_SCORE_THRESHOLD  # noqa: E402
from docs_assistant import answer_question as simulated_answer_question, VERSION as GENERATOR_VERSION_CONST  # noqa: E402
from tracing import write_traces_jsonl  # noqa: E402

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DOCS_DIR = os.path.join(BASE_DIR, "docs")
TRACES_PATH = os.path.join(BASE_DIR, "data", "traces.jsonl")

GENERATION_SEED = 20260915
TOTAL_TRACES = 1200
NUM_DAYS = 7
END_DATE = datetime(2026, 9, 14, 23, 0, 0)  # "yesterday" relative to today's date, 2026-09-15

RETRIEVER_VERSION = "rrf_fusion_v1_k60"  # src/fusion_retriever.py, shipped in Week 4
GENERATOR_VERSION = GENERATOR_VERSION_CONST  # src/docs_assistant.py -- see its module docstring

# channel -> (probability, sdk_version passed)
CHANNELS = [
    ("web_widget", 0.62, "v3"),
    ("slack_integration", 0.38, None),  # never updated to pass a filter
]

# Each intent: (id, weight, [phrasing variants])
INTENTS = [
    ("retry_backoff_default", 9.0, [
        "What is the default value of retry_backoff_ms in Client.send()?",
        "what's the default retry_backoff_ms",
        "How long does the client wait between retries by default?",
        "default retry_backoff_ms value pls",
        "if i dont set retry_backoff_ms what does it default to",
    ]),
    ("timeout_ms_default", 8.0, [
        "What is the default value of timeout_ms in Client.send()?",
        "default timeout_ms for send()",
        "how long until Client.send() times out by default",
        "whats the timeout_ms default value",
    ]),
    ("max_retries_default", 5.0, [
        "What is the default value of max_retries in Client.send()?",
        "how many times will send() retry by default",
        "default max_retries value",
    ]),
    ("auth_how_to", 10.0, [
        "How do I authenticate with the Acme SDK?",
        "how does authentication work",
        "how do i set up my api key",
        "what's the easiest way to authenticate a client",
    ]),
    ("auth_required_param", 6.0, [
        "What parameter is required when creating an AuthConfig?",
        "is api_key required for AuthConfig",
        "what fields does AuthConfig need",
    ]),
    ("token_refresh_default", 4.0, [
        "What is the default token_refresh_ms for AuthConfig?",
        "how often does the session token refresh by default",
        "default value of token_refresh_ms",
    ]),
    ("region_default", 2.0, [
        "What is the default region in AuthConfig?",
        "default region value for AuthConfig",
    ]),
    ("rotate_api_key", 5.0, [
        "How do I rotate my API key if it's compromised?",
        "steps to rotate a leaked api key",
        "my key leaked, what do i do",
    ]),
    ("client_close", 3.0, [
        "What does Client.close() do?",
        "when should I call close() on my client",
        "does close() take any parameters",
    ]),
    ("stream_return_type", 5.0, [
        "What does Client.stream() return?",
        "what type of object does stream() give me back",
        "how do i get streaming responses",
    ]),
    ("chunk_size_default", 3.0, [
        "What is the default chunk_size for Client.stream()?",
        "how big is each chunk yielded by stream() unless I override it",
        "default chunk_size value",
    ]),
    ("is_final_meaning", 2.0, [
        "What does the is_final field on a StreamChunk indicate?",
        "how do I know when a stream has finished sending chunks",
    ]),
    ("body_encoding_default", 4.0, [
        "What is the default body_encoding value in RequestOptions?",
        "is the request body sent as json or form by default",
        "default body_encoding",
    ]),
    ("headers_query_params_default", 2.0, [
        "What are the default values of headers and query_params in RequestOptions?",
        "default headers value in RequestOptions",
    ]),
    ("idempotency_key", 4.0, [
        "What does passing the same X-Idempotency-Key header guarantee?",
        "can I safely retry a send() call twice without it running twice server-side",
        "does idempotency key prevent duplicate requests",
    ]),
    ("auth_error_exception", 5.0, [
        "Which exception is raised when the api_key is missing or invalid?",
        "what error fires if my api key is wrong",
    ]),
    ("validation_error_exception", 3.0, [
        "Which exception is raised when a required parameter is missing or malformed?",
        "if I pass a malformed parameter what does the SDK throw",
    ]),
    ("timeout_error_exception", 3.0, [
        "Which exception is raised when timeout_ms is exceeded?",
        "what exception do I get on a timeout",
    ]),
    ("status_code_meaning", 4.0, [
        "What does a status_code other than 200 mean on a Response?",
        "if response status code isn't 200 what does that mean",
    ]),
    ("response_required_fields", 3.0, [
        "Which fields are required in the Response object?",
        "what fields are always present on a Response",
    ]),
    ("vague_how_to_use", 3.0, [
        "how do I use this SDK",
        "how does this whole thing work",
        "quick start please",
    ]),
    # deliberately out-of-corpus -- should be correctly refused
    ("rate_limit_oc", 3.0, [
        "What is the rate limit for Client.send()?",
        "how many requests per second can I make",
    ]),
    ("concurrency_oc", 2.0, [
        "How many concurrent requests does the SDK support?",
    ]),
    ("sla_oc", 2.0, [
        "What uptime SLA does the SDK guarantee?",
    ]),
    ("version_string_oc", 2.0, [
        "Does the SDK support v3.2.0 of the API?",
        "is v3.2.0 compatible with this client",
    ]),
]


def _build_retriever():
    pages = load_pages(DOCS_DIR)
    chunks = chunk_pages(pages, StructureAwareChunker())
    combined = chunks + build_legacy_v2_chunks()
    return RRFRetriever(combined)


def _weighted_choice(rng, items_with_weights):
    total = sum(w for _, w, _ in items_with_weights)
    r = rng.uniform(0, total)
    upto = 0
    for item_id, weight, variants in items_with_weights:
        upto += weight
        if r <= upto:
            return item_id, variants
    return items_with_weights[-1][0], items_with_weights[-1][2]


def _pick_channel(rng):
    r = rng.random()
    upto = 0
    for name, prob, sdk_version in CHANNELS:
        upto += prob
        if r <= upto:
            return name, sdk_version
    return CHANNELS[-1][0], CHANNELS[-1][2]


def generate():
    retriever = _build_retriever()
    rng = random.Random(GENERATION_SEED)

    traces = []
    for i in range(TOTAL_TRACES):
        day = int(i / TOTAL_TRACES * NUM_DAYS)  # spreads evenly across the 7-day window, oldest first
        seconds_into_day = rng.randint(0, 86399)
        timestamp = END_DATE - timedelta(days=(NUM_DAYS - 1 - day)) + timedelta(seconds=seconds_into_day)

        channel, sdk_version = _pick_channel(rng)
        intent_id, variants = _weighted_choice(rng, INTENTS)
        question = rng.choice(variants)

        start = time.perf_counter()
        result = simulated_answer_question(question, retriever, sdk_version=sdk_version)
        top3 = retriever.search(question, top_k=3, sdk_version=sdk_version)
        latency_ms = (time.perf_counter() - start) * 1000

        trace = {
            "trace_id": f"trace-{i:05d}",
            "timestamp": timestamp.isoformat(),
            "day": day,
            "question": question,
            "sdk_version_filter": sdk_version,
            "answered": result["answered"],
            "raw_output": result["answer"],
            "retriever_version": RETRIEVER_VERSION,
            "generator_version": GENERATOR_VERSION,
            "min_score_threshold": MIN_SCORE_THRESHOLD,
            "retrieved": [
                {
                    "rank": r.rank,
                    "chunk_id": r.chunk.chunk_id,
                    "score": round(r.score, 4),
                    "sdk_version": r.chunk.sdk_version,
                    "source_file": r.chunk.source_file,
                }
                for r in top3
            ],
            "cited_chunk_id": result["chunk_id"],
            "latency_ms": round(latency_ms, 4),
            "_channel": channel,  # internal-only, not part of the persisted trace schema
            "_intent_id": intent_id,
        }
        traces.append(trace)

    write_traces_jsonl(TRACES_PATH, traces)
    return traces


if __name__ == "__main__":
    traces = generate()
    print(f"Wrote {len(traces)} traces to {TRACES_PATH}")
    print(f"Generation seed: {GENERATION_SEED}")
