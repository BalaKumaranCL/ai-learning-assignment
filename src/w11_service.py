"""The Week-11 "production" docs assistant: the same retriever and refuse
rule as Weeks 4-6, wrapped so every request leaves a full trace -- one span
per stage (retrieval / generation / tools) with latency, tokens, dollars,
the prompt version and the retrieved context ids.

Like every earlier week there is no live model here (see llm_sim.py): the
"generation" stage is a deterministic stand-in, and latency and dollar
figures are MODELLED from documented constants below, not measured from a
provider. What is real is the shape: stages, ids, versions, the arithmetic.

Prompt versions live in PROMPTS. A request is always answered by exactly one
version, and that version is written into the trace -- which is what lets a
log line be tied back to the behaviour that produced it.
"""

import hashlib
import os
import re

import deprecations
from loader import load_pages
from chunkers import StructureAwareChunker, chunk_pages
from legacy_v2 import build_legacy_v2_chunks
from fusion_retriever import RRFRetriever
from docs_assistant import _confidence_score, _refusal_text
from generator import MIN_SCORE_THRESHOLD
from llm_sim import estimate_tokens, PRICE_PER_1K_INPUT_USD, PRICE_PER_1K_OUTPUT_USD
from models import Chunk

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "docs")

RETRIEVER_VERSION = "rrf_fusion_v1_k60"
TOP_K = 3

# ---- Documented ASSUMPTIONS (not billing data). Change them and every
# downstream cost/latency number moves with them. ----
EMBED_USD_PER_1K_TOKENS = 0.00002      # hosted query-embedding price
VECTOR_QUERY_USD = 0.000004            # hosted vector-store read, per query
TOOL_CALL_USD = 0.00005                # hosted tool/API call, per call
RETRIEVAL_BASE_MS = 14.0
RETRIEVAL_MS_PER_CHUNK_SCANNED = 0.9
GENERATION_BASE_MS = 220.0
GENERATION_MS_PER_OUTPUT_TOKEN = 11.0
GENERATION_MS_PER_INPUT_TOKEN = 0.35
TOOL_CALL_MS = 40.0
SLOW_PROVIDER_RATE = 0.012             # ~1 in 83 generations hit a slow provider response
SLOW_PROVIDER_MULTIPLIER = 3.5

PROMPTS = {
    "docs_v1": (
        "You are the Acme SDK docs assistant. Answer ONLY from the retrieved "
        "context and cite the chunk id. If the context does not cover the "
        "question, refuse. For code-sample requests, give a runnable Python "
        "sample; if the context has none, write one from your knowledge of "
        "the SDK."
    ),
}
PROMPTS["docs_v2"] = (
    PROMPTS["docs_v1"].replace(
        " if the context has none, write one from your knowledge of the SDK.", " if the context has none, say so."
    )
    + " Never output a method, parameter or class that the deprecation tool "
    "reports as deprecated unless the user asked for SDK v2. Every code "
    "sample is checked with the deprecation tool before it is returned. If "
    "the user gives no SDK version, answer for the current version (v3)."
)

# What each prompt version DOES, as data -- so a trace's prompt_version
# tells you exactly which behaviours were switched on for that request.
FEATURES = {
    "docs_v1": {},
    "docs_v2": {
        "default_version_filter": "v3",   # retrieval: unfiltered callers get current docs, not archived v2
        "code_sample_gate": 0.10,         # retrieval: code samples need a fenced sample + this confidence
        "code_sample_top_k": 5,           # retrieval: sample chunks rank below prose chunks, so look 5 deep
        "strip_request_words": True,      # retrieval: "give me a code sample for X" is searched as "X"
        "no_memory_samples": True,        # generation: never write a sample "from memory"
        "lint_tool": True,                # tools: check_deprecation on every code sample
    },
}
ACTIVE_PROMPT_VERSION = "docs_v2"   # bumped from docs_v1 on 2026-10-21 (the incident fix)


def build_archive_chunks():
    """Simulated archived-v2 pages that only the Week-11 service indexes
    (like legacy_v2.py, a stand-in: the kind of old page a docs crawler
    keeps). They are what makes a stale sample retrievable."""

    def c(i, text, version, anchor, src, page_id):
        return Chunk(chunk_id=f"{page_id}::archive::{i}", text=text, source_file=src,
                     page_id=page_id, sdk_version=version, page_type="guide",
                     anchor=anchor, strategy="w11_archive")

    return [
        c(0,
          "Sending a message with the v2 client (archived code sample).\n\n```python\n"
          "from acme_sdk import Client, AuthConfig\n\n"
          "client = Client(AuthConfig(token=\"sk_live_example\"))\n"
          "reply = client.sendMessage(\"hello\")\n"
          "print(reply.body)\n```\n",
          "v2", "Sending a message > Code sample (v2)", "client_v2_archive.md", "client_v2"),
        c(1,
          "Streaming with the v2 client (archived code sample).\n\n```python\n"
          "from acme_sdk import Client, AuthConfig\n\n"
          "client = Client(AuthConfig(token=\"sk_live_example\"))\n"
          "stream = client.pollStream(\"hello\")\n"
          "while not stream.done:\n    print(stream.next())\n```\n",
          "v2", "Streaming > Code sample (v2)", "client_v2_archive.md", "client_v2"),
        c(2,
          "Migration note: Client.sendMessage is deprecated in v3. It was "
          "renamed to Client.send; the request shape is unchanged. "
          "Client.pollStream is deprecated too, use Client.stream instead.",
          "v3", "Migration guide > Renamed methods", "migration_v3.md", "migration_v3"),
    ]


_CODE_SAMPLE_RE = re.compile(
    r"\b(code sample|sample code|snippet|code example|example code|show me (the )?code|write (me )?(a )?(code|script))\b",
    re.IGNORECASE)
_MIGRATION_RE = re.compile(r"\b(deprecat\w*|migrat\w*|renamed|replac\w+)\b", re.IGNORECASE)


def classify_input(question):
    if _CODE_SAMPLE_RE.search(question):
        return "code_sample"
    if _MIGRATION_RE.search(question):
        return "migration"
    return "factual"


_ASKS_V2_RE = re.compile(r"\b(v2|legacy|2\.x)\b", re.IGNORECASE)
_REQUEST_WORDS_RE = re.compile(
    r"^(?:(?:give|show|write)\s+me\s+)?(?:(?:a|an|the)\s+)?(?:code sample|sample code|code snippet|snippet|code example|example code)s?\s*(?:for|of|to|that)?\s*|"
    r"^(?:(?:give|show|write)\s+me\s+)(?:(?:a|an|the)\s+)?",
    re.IGNORECASE)


def effective_filter(prompt_version, sdk_filter, question):
    """The filter actually applied to retrieval. v1 applies exactly what the
    caller sent. v2 fills in the current version for callers that sent none,
    unless the question itself asks about v2."""
    default = FEATURES[prompt_version].get("default_version_filter")
    if sdk_filter is None and default and not _ASKS_V2_RE.search(question):
        return default
    return sdk_filter


_FENCE_RE = re.compile(r"```python\n.*?```", re.DOTALL)

# What a model "remembers" when the context holds no sample: the pre-fix
# SDK. Same stale sample as mcp_llm_sim.stale_prior_answer.
MEMORY_SAMPLE = (
    "```python\nfrom acme_sdk import Client, AuthConfig\n\n"
    "client = Client(AuthConfig(token=TOKEN))\nreply = client.sendMessage(prompt)\n```"
)

_index = None


def _get_index():
    global _index
    if _index is None:
        pages = load_pages(DOCS_DIR)
        chunks = chunk_pages(pages, StructureAwareChunker()) + build_legacy_v2_chunks() + build_archive_chunks()
        _index = RRFRetriever(chunks)
    return _index


def all_chunks():
    return {c.chunk_id: c for c in _get_index().chunks}


def _jitter(trace_id, salt):
    h = int(hashlib.sha256(f"{trace_id}:{salt}".encode()).hexdigest()[:8], 16)
    return h / 0xFFFFFFFF


def _retrieval_span(trace_id, question, filter_applied, results, index_size, top_k):
    q_tokens = estimate_tokens(question)
    ms = (RETRIEVAL_BASE_MS + RETRIEVAL_MS_PER_CHUNK_SCANNED * index_size) * (0.85 + 0.4 * _jitter(trace_id, "r"))
    return {
        "name": "retrieval", "stage": "retrieval",
        "latency_ms": round(ms, 1), "tokens_in": q_tokens, "tokens_out": 0,
        "cost_usd": round(q_tokens / 1000 * EMBED_USD_PER_1K_TOKENS + VECTOR_QUERY_USD, 8),
        "retriever_version": RETRIEVER_VERSION, "top_k": top_k,
        "sdk_version_filter_applied": filter_applied,
        "chunk_ids": [r.chunk.chunk_id for r in results],
    }


def _generation_span(trace_id, prompt_version, context_text, question, answer):
    t_in = estimate_tokens(PROMPTS[prompt_version]) + estimate_tokens(question) + estimate_tokens(context_text)
    t_out = estimate_tokens(answer)
    ms = (GENERATION_BASE_MS + GENERATION_MS_PER_OUTPUT_TOKEN * t_out + GENERATION_MS_PER_INPUT_TOKEN * t_in) \
        * (0.85 + 0.4 * _jitter(trace_id, "g"))
    if _jitter(trace_id, "slow") < SLOW_PROVIDER_RATE:
        ms *= SLOW_PROVIDER_MULTIPLIER
    cost = t_in / 1000 * PRICE_PER_1K_INPUT_USD + t_out / 1000 * PRICE_PER_1K_OUTPUT_USD
    return {
        "name": "generation", "stage": "generation",
        "latency_ms": round(ms, 1), "tokens_in": t_in, "tokens_out": t_out,
        "cost_usd": round(cost, 8), "model": "haiku-class (assumed)", "prompt_version": prompt_version,
    }


def _lint_span(trace_id, found):
    return {
        "name": "tool:check_deprecation", "stage": "tools",
        "latency_ms": round(TOOL_CALL_MS * (0.85 + 0.4 * _jitter(trace_id, "t")), 1),
        "tokens_in": 0, "tokens_out": 0, "cost_usd": TOOL_CALL_USD,
        "calls": 1, "deprecated_found": found,
    }


def _generate(trace_id, prompt_version, question, input_type, results, confidence, requested_filter):
    """Returns (answered, answer, cited_chunk_id, tool_spans)."""
    feat = FEATURES[prompt_version]
    gate = MIN_SCORE_THRESHOLD
    if input_type == "code_sample" and "code_sample_gate" in feat:
        gate = feat["code_sample_gate"]
    if not results or confidence < gate:
        return False, _refusal_text(question), None, []
    top = results[0].chunk

    if input_type != "code_sample":
        return True, top.text.strip(), top.chunk_id, []

    for r in results:
        fence = _FENCE_RE.search(r.chunk.text)
        if fence:
            answer = f"Here is a sample from the docs ({r.chunk.chunk_id}):\n\n{fence.group(0)}"
            cited = r.chunk.chunk_id
            break
    else:
        if feat.get("no_memory_samples"):
            return False, "The retrieved documentation has no code sample for that, so I won't write one from memory.", None, []
        return True, f"Here is a sample based on what I remember of the SDK (no source cited):\n\n{MEMORY_SAMPLE}", None, []

    tool_spans = []
    if feat.get("lint_tool"):
        found = deprecations.find_deprecated_symbols(answer)
        tool_spans.append(_lint_span(trace_id, found))
        if found and requested_filter != "v2":
            names = ", ".join(found)
            repl = ", ".join(deprecations.BY_NAME[n]["replacement"] for n in found)
            return True, (f"The only sample I found uses {names}, which is deprecated in v3. "
                          f"Use {repl} instead."), None, tool_spans
    return True, answer, cited, tool_spans


def run_request(req, trace_id, prompt_version=None):
    """Answer one request and return the full trace dict.

    req: {ts, user_id, app, question, sdk_version_filter}
    """
    prompt_version = prompt_version or ACTIVE_PROMPT_VERSION
    index = _get_index()
    question = req["question"]
    input_type = classify_input(question)

    sdk_filter = req.get("sdk_version_filter")
    applied = effective_filter(prompt_version, sdk_filter, question)
    search_query = question
    if input_type == "code_sample" and FEATURES[prompt_version].get("strip_request_words"):
        search_query = _REQUEST_WORDS_RE.sub("", question).strip() or question
    top_k = FEATURES[prompt_version].get("code_sample_top_k", TOP_K) if input_type == "code_sample" else TOP_K
    results = index.search(search_query, top_k=top_k, sdk_version=applied)
    confidence = _confidence_score(index, search_query, results[0].chunk.chunk_id, applied) if results else 0.0

    answered, answer, cited, tool_spans = _generate(
        trace_id, prompt_version, question, input_type, results, confidence, sdk_filter)

    context_text = "\n\n".join(r.chunk.text for r in results)
    spans = [
        _retrieval_span(trace_id, question, applied, results, len(index.chunks), top_k),
        _generation_span(trace_id, prompt_version, context_text, question, answer),
    ] + tool_spans

    return {
        "trace_id": trace_id,
        "ts": req["ts"],
        "user_id": req["user_id"],
        "app": req["app"],
        "prompt_version": prompt_version,
        "retriever_version": RETRIEVER_VERSION,
        "sdk_version_filter": sdk_filter,
        "sdk_version_filter_applied": applied,
        "question": question,
        "input_type": input_type,
        "answered": answered,
        "answer": answer,
        "cited_chunk_id": cited,
        "retrieved_chunk_ids": [r.chunk.chunk_id for r in results],
        "retrieved_sdk_versions": [r.chunk.sdk_version for r in results],
        "retrieval_confidence": round(confidence, 4),
        "spans": spans,
        "totals": {
            "latency_ms": round(sum(s["latency_ms"] for s in spans), 1),
            "tokens_in": sum(s["tokens_in"] for s in spans),
            "tokens_out": sum(s["tokens_out"] for s in spans),
            "cost_usd": round(sum(s["cost_usd"] for s in spans), 8),
        },
    }
