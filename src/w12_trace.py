"""Week 12: one trace id from question in to answer out, across the agent hop
AND the MCP hop (the Week-11 per-request logging, extended to cross a process
boundary).

A Trace is a flat list of spans. Every span has: span_id, parent_span_id,
name, stage, side ('engine' | 'server'), latency_ms, tokens_in/out, cost_usd,
and `latency_kind` -- 'measured' (a real stopwatch on real work: retrieval,
the MCP round trip, the code check) or 'modelled' (the stand-in model's
latency, from documented constants in w12_engine.py; the repo has no live LLM).

Two writers exist and both redact ON WRITE (w12_redact):
  * TraceWriter  -- the engine's request log (one JSON line per request)
  * the MCP server appends its own span lines with the same redactor
The server's spans come back inside each tool result as `_server_span`, so a
request's trace shows both sides; whether the server's copy carries the SAME
trace id is exactly what the `trace_unbroken` assertion checks.
"""

import hashlib
import json
import os
import threading
import time
from contextlib import contextmanager

from w12_redact import redact_deep

_LOCK = threading.Lock()


def new_trace_id(key):
    return "t_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:10]


class Trace:
    def __init__(self, trace_id, config_name=""):
        self.trace_id = trace_id
        self.config_name = config_name
        self.spans = []
        self._n = 0
        self.started = time.perf_counter()

    def next_span_id(self):
        self._n += 1
        return f"{self.trace_id}.s{self._n}"

    def add(self, name, stage, parent=None, side="engine", latency_ms=0.0, tokens_in=0, tokens_out=0,
            cost_usd=0.0, kind="measured", span_id=None, **attrs):
        span = {
            "span_id": span_id or self.next_span_id(), "parent_span_id": parent, "trace_id": self.trace_id,
            "name": name, "stage": stage, "side": side, "latency_ms": round(latency_ms, 2),
            "latency_kind": kind, "tokens_in": tokens_in, "tokens_out": tokens_out, "cost_usd": round(cost_usd, 8),
        }
        span.update(attrs)
        self.spans.append(span)
        return span

    @contextmanager
    def span(self, name, stage, parent=None, **attrs):
        """Measured span: `with trace.span('resolve_version', 'resolve') as sp:` then fill sp[...] inside."""
        sp = self.add(name, stage, parent=parent, **attrs)
        t0 = time.perf_counter()
        try:
            yield sp
        finally:
            sp["latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)

    def merge_server_span(self, server_span, parent):
        """Attach the span the MCP server reported for one call. Never rewritten -- if the
        server saw no trace id, that is recorded as-is (and the assertion will say so)."""
        sp = dict(server_span)
        sp.setdefault("side", "server")
        sp["reported_parent_span_id"] = sp.get("parent_span_id")
        sp["parent_span_id"] = parent
        sp.setdefault("tokens_in", 0)
        sp.setdefault("tokens_out", 0)
        self.spans.append(sp)
        return sp

    def totals(self):
        """End-to-end latency is the CRITICAL PATH: the independent tool calls in one lap run in parallel,
        so a lap costs its slowest call, not the sum. Container spans (request / agent) are not work."""
        lap_max, serial = {}, 0.0
        for s in self.spans:
            if s.get("side") != "engine" or s["stage"] in ("request", "agent"):
                continue
            if "lap" in s:
                lap_max[s["lap"]] = max(lap_max.get(s["lap"], 0.0), s["latency_ms"])
            else:
                serial += s["latency_ms"]
        return {
            "latency_ms": round(serial + sum(lap_max.values()), 2),
            "tokens_in": sum(s.get("tokens_in", 0) for s in self.spans),
            "tokens_out": sum(s.get("tokens_out", 0) for s in self.spans),
            "cost_usd": round(sum(s.get("cost_usd", 0.0) for s in self.spans), 8),
        }

    def by_stage(self):
        out = {}
        for s in self.spans:
            st = out.setdefault(s["stage"], {"latency_ms": 0.0, "cost_usd": 0.0, "tokens_in": 0, "tokens_out": 0, "spans": 0})
            st["latency_ms"] += s["latency_ms"] if s.get("side") == "engine" else 0.0
            st["cost_usd"] += s.get("cost_usd", 0.0)
            st["tokens_in"] += s.get("tokens_in", 0)
            st["tokens_out"] += s.get("tokens_out", 0)
            st["spans"] += 1
        return out


class TraceWriter:
    """Append-only JSONL; every record is redacted deeply BEFORE it touches disk."""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)

    def write(self, record):
        line = json.dumps(redact_deep(record), ensure_ascii=False)
        with _LOCK:
            with open(self.path, "a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")

    def reset(self):
        with open(self.path, "w", encoding="utf-8"):
            pass


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]
