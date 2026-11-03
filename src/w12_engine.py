"""Week 12: THE integrated engine -- the one entry point.

    question in -> redact -> RESOLVE THE VERSION -> agent loop (RAG over MCP, 4 tools)
                -> compose -> one redacted trace out

Everything from Weeks 3-11 runs behind `Engine.ask`:
  Week 3-4  RAG        w12_index (structure-aware chunks, RRF, version metadata filter)
  Week 7    agent      w12_agent (hand-built loop)
  Week 6    evals      w12_eval (25-40 cases, assertions before the judge)
  Week 8    trajectory w12_trajectory
  Week 9    MCP        mcp_servers/w12_sdk_docs_server.py (exposed) + w12_mcp.W12Host (consumed, tools discovered at runtime)
  Week 11   logging    w12_trace + w12_redact (one trace id, cost/latency per span, redact on write)

Config
------
`NAIVE` is what the first end-to-end wiring did: each flag below is OFF, and each
one corresponds to a seam found while wiring (see output/w12/seams.md). `FIXED`
turns all eight on. They are flags, not two code paths, so the before/after
number in the report is the SAME system run twice -- and the ablation can turn
them on one at a time to see which flag fixed which failure.
"""

import asyncio
import dataclasses
import os
import time
from dataclasses import dataclass

import w12_agent as agent
import w12_answer as answer
import w12_symbols as sym
import w12_versions as V
from llm_sim import estimate_tokens
from w12_llm import SYSTEM_PROMPT, model_call
from w12_mcp import W12Host
from w12_redact import redact, strip_markers
from w12_trace import Trace, TraceWriter, new_trace_id

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MCP_CONFIG = os.path.join(BASE_DIR, "mcp_config.w12.json")
RUNS_DIR = os.path.join(BASE_DIR, "output", "w12", "runs")


@dataclass(frozen=True)
class Config:
    name: str
    smart_resolve: bool      # S4  resolve the version from several sources; ask if unknown (else: only the explicit field, default to latest)
    inject_version: bool     # S3  the agent puts the RESOLVED version into every tool call (else: only if the question text says one)
    strict_server: bool      # S2  the server refuses a call with no version (else: no version = search every version)
    minor_filter: bool       # S5  filter by version RANGE as well as major (else: major only)
    trace_hop: bool          # S10 pass the trace id across the MCP hop (else: the server's spans are orphaned)
    redact_hop: bool         # S11 redact BEFORE the question leaves the process and on the server's own log write
    code_gate: bool          # S12 verify every code sample (parse, imports, symbols, run) before emitting it
    relevance_floor: bool    # S13 never offer a code sample that shares no content word with the question (found by the version sweep)

    FLAGS = ("smart_resolve", "inject_version", "strict_server", "minor_filter", "trace_hop", "redact_hop", "code_gate", "relevance_floor")

    def server_env(self, span_log):
        return {"W12_VERSION_POLICY": "strict" if self.strict_server else "lenient",
                "W12_MINOR_FILTER": "1" if self.minor_filter else "0",
                "W12_SERVER_REDACT": "1" if self.redact_hop else "0",
                "W12_SPAN_LOG": span_log, **({"W12_MANIFEST": os.environ["W12_MANIFEST"]} if os.environ.get("W12_MANIFEST") else {})}

    def flags(self):
        return {f: getattr(self, f) for f in self.FLAGS}


NAIVE = Config("naive", *(False,) * 8)
FIXED = Config("fixed", *(True,) * 8)


def with_flags(base, name, **changes):
    return dataclasses.replace(base, name=name, **changes)


class Engine:
    def __init__(self, config, run_dir=None):
        self.config = config
        self.run_dir = run_dir or os.path.join(RUNS_DIR, config.name)
        os.makedirs(self.run_dir, exist_ok=True)
        self.request_log = os.path.join(self.run_dir, "requests.jsonl")
        self.server_log = os.path.join(self.run_dir, "mcp_server_spans.jsonl")
        for p in (self.request_log, self.server_log):
            open(p, "w").close()
        self.writer = TraceWriter(self.request_log)
        self.host = None

    async def __aenter__(self):
        self.host = W12Host(MCP_CONFIG, extra_env=self.config.server_env(self.server_log))
        await self.host.connect()
        return self

    async def __aexit__(self, *exc):
        await self.host._stack.aclose()

    # ------------------------------------------------------------------
    async def ask(self, request):
        """request: {question, sdk_version?, case_id?} -> result dict (also written to requests.jsonl, redacted)."""
        cfg = self.config
        question = request["question"]
        trace = Trace(new_trace_id(f"{cfg.name}|{request.get('case_id') or question}"), cfg.name)
        root = trace.add("request", "request", latency_ms=0.0)

        with trace.span("redact_input", "redact", parent=root["span_id"]) as sp:
            safe_q, findings = redact(question)
            sp["pii_kinds"] = sorted(set(findings))
        search_q = strip_markers(safe_q)
        outbound_q = search_q if cfg.redact_hop else question

        with trace.span("resolve_version", "resolve", parent=root["span_id"]) as sp:
            resolution = V.resolve_version(question, request.get("sdk_version"), smart=cfg.smart_resolve)
            named = [n for n in sym.extract_symbols(question) if "." in n["id"]]
            intent = agent.classify_intent(question, named)
            sp.update(version=resolution["version"], source=resolution["source"], confidence=resolution["confidence"],
                      target_version=resolution["target_version"], intent=intent, named=[n["id"] for n in named])

        scope = resolution["version"]
        if scope is None and resolution["target_version"]:
            scope = resolution["target_version"]
            resolution = dict(resolution, version=scope, source="target_only", confidence="medium",
                              evidence="no caller version; answering for the version the question asks about")
        ctx_ev = {"question": safe_q, "resolution": resolution, "scope": scope, "target": resolution["target_version"],
                  "intent": intent, "named": named, "exists": {}, "lifecycle": {}, "docs": [], "samples": [], "upgrade": [],
                  "chosen_sample": None, "sample_rejected": None, "wants_code": False, "check_version": scope, "topic_terms": set()}
        calls, st = [], None

        if scope is not None:
            use_target = resolution["target_version"] and intent in ("status", "migration") and resolution["target_version"] != scope
            check_version = resolution["target_version"] if use_target else scope
            agent_span = trace.add("agent_loop", "agent", parent=root["span_id"])
            t0 = time.perf_counter()
            st, calls = await agent.run_agent(
                {"question": search_q, "outbound_q": outbound_q, "intent": intent, "named": named, "scope": scope,
                 "target": resolution["target_version"], "check_version": check_version, "config": cfg,
                 "mentioned_version": _mentioned(question)},
                self.host, trace, agent_span["span_id"])
            agent_span["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
            ctx_ev.update(exists=st.exists, lifecycle=st.lifecycle, docs=st.docs, samples=st.samples, upgrade=st.upgrade,
                          chosen_sample=st.chosen, sample_rejected=st.rejected if cfg.code_gate else None,
                          wants_code=st.wants_code(), check_version=check_version, topic_terms=st._topic_terms(),
                          caller_status={n["id"]: (st.lifecycle.get(n["id"]) or {}).get("status") for n in named})

        composed = answer.compose(ctx_ev)
        evidence_text = "\n".join(c["text"] for k in ("docs", "samples", "upgrade") for c in ctx_ev[k])
        model_call(trace, "compose", "generate", root["span_id"], f"{SYSTEM_PROMPT}\nQ: {safe_q}\n{evidence_text}", composed["answer"], "compose")

        totals = trace.totals()
        result = {
            "trace_id": trace.trace_id, "case_id": request.get("case_id"), "config": cfg.name, "question": safe_q,
            "sdk_version_sent": request.get("sdk_version"), "resolution": resolution, "scope": scope, "intent": intent,
            "named": [n["id"] for n in named], "answer": composed["answer"], "answered": composed["answered"],
            "clarification": composed["clarification"], "citations": composed["citations"],
            "tool_calls": calls, "laps": sum(1 for s in trace.spans if s["stage"] == "plan"),
            "retrieved": [{"chunk_id": c["chunk_id"], "page_type": c["page_type"], "sdk_version": c["sdk_version"],
                           "valid_from": c["valid_from"], "valid_to": c["valid_to"], "kind": k}
                          for k in ("docs", "samples", "upgrade") for c in ctx_ev[k]],
            "chosen_sample": ctx_ev["chosen_sample"]["chunk_id"] if ctx_ev["chosen_sample"] else None,
            "sample_rejected": ctx_ev["sample_rejected"],
            "lifecycle": {k: v for k, v in ctx_ev["lifecycle"].items()},
            "exists": {k: {"status": v.get("status"), "nearest": v.get("nearest")} for k, v in ctx_ev["exists"].items()},
            "spans": trace.spans, "totals": totals, "by_stage": trace.by_stage(),
        }
        self.writer.write({k: v for k, v in result.items() if k != "retrieved"} | {"question_raw": question})
        return result


def _mentioned(question):
    m = V._MENTION_RE.search(question or "")
    v = V.parse(m.group(1)) if m else None
    return V.fmt((v[0], v[1] or 0)) if v else None


async def run_batch(config, requests, run_dir=None):
    async with Engine(config, run_dir) as engine:
        discovery = engine.host.discovery
        out = [await engine.ask(r) for r in requests]
    return out, discovery


def run_batch_sync(config, requests, run_dir=None):
    return asyncio.run(run_batch(config, requests, run_dir))
