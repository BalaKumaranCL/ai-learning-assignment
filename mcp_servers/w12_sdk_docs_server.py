"""Week 12: the SDK-docs MCP server -- OUR OWN server, exposing a genuine
capability (version-scoped doc search) plus the two lookups an SDK answer
needs: "when was this deprecated / removed / what replaces it" and "does this
name exist in THIS version". Called by our own agent AND by any foreign MCP
client (see reviewer_client.py -- it uses nothing from this repo).

No model call lives here: a server exposes capabilities, the host runs the model.

Every tool takes two optional correlation arguments, `trace_id` and
`parent_span_id`. The server writes its own span (latency, cost, what it was
asked) to its OWN log AND returns it inside the result as `_server_span`, so a
request's trace shows both sides of the hop with one trace id.

Behaviour switches (environment, so the Week 12 before/after can run the SAME
server both ways -- the same pattern as Week 9's DOCS_SERVER_STYLE):
  W12_VERSION_POLICY  strict (default)  a call with no usable sdk_version is REFUSED; the server never guesses
                      lenient           Week 9's behaviour: no version = search every version at once
  W12_MINOR_FILTER    1 (default)       also filter by version RANGE (a 2.4 caller never gets a 2.6 section)
                      0                 filter by major version only
  W12_SERVER_REDACT   1 (default)       redact secrets before writing the server's own log
                      0                 write the inputs exactly as received
  W12_SPAN_LOG        path of the server's own JSONL span log
  W12_MANIFEST        alternate symbols.json (the v3.1 drill)
"""

import difflib
import json
import os
import re
import sys
import time

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))

from mcp.server.fastmcp import FastMCP  # noqa: E402
from mcp.server.fastmcp.exceptions import ToolError  # noqa: E402

import w12_index as ix  # noqa: E402
import w12_symbols as sym  # noqa: E402
from w12_redact import redact_deep  # noqa: E402
from w12_versions import fmt, parse  # noqa: E402

POLICY = os.environ.get("W12_VERSION_POLICY", "strict")
MINOR_FILTER = os.environ.get("W12_MINOR_FILTER", "1") == "1"
REDACT = os.environ.get("W12_SERVER_REDACT", "1") == "1"
SPAN_LOG = os.environ.get("W12_SPAN_LOG", os.path.join(BASE, "output", "w12", "mcp_server_spans.jsonl"))
MCP_CALL_USD = 0.00002        # ASSUMED price of one hosted tool call (documented, not billing data)
KIND_TO_TYPES = {"docs": {"reference", "changelog"}, "samples": {"sample"}, "upgrade": {"migration", "changelog"}}

mcp = FastMCP("acme-sdk-docs")
_counter = [0]


def _version_arg(sdk_version, tool):
    """-> (major, minor) or raise. In strict mode a missing version is an error, not a default."""
    if sdk_version in (None, ""):
        if POLICY == "strict":
            raise ToolError(
                f"VERSION_REQUIRED: {tool} needs the caller's SDK version in `sdk_version` (for example '2.4' or '3.0'). "
                "2.x and 3.0 are both live and have different APIs, so I will not guess one. "
                "Resolve the version first (pip show acme-sdk) and call again.")
        return None
    v = parse(sdk_version)
    if v is None:
        raise ToolError(f"UNSUPPORTED_VERSION: {sdk_version!r} is not a version I have docs for. Docs exist for 2.x (2.0-{sym.latest(2)}) and 3.0.")
    return (v[0], v[1] if v[1] is not None else 0)


def _log_span(tool, started, trace_id, parent_span_id, received_args, extra=None):
    _counter[0] += 1
    tid = trace_id or ""
    span = {
        "trace_id": tid, "span_id": f"{tid or 'untraced'}.srv{_counter[0]}", "parent_span_id": parent_span_id or None,
        "name": f"mcp:{tool}", "stage": "tool", "side": "server", "tool": tool,
        "latency_ms": round((time.perf_counter() - started) * 1000, 2), "latency_kind": "measured",
        "cost_usd": MCP_CALL_USD, "tokens_in": 0, "tokens_out": 0,
    }
    if extra:
        span.update(extra)
    record = dict(span, args_received=received_args, ts=time.strftime("%Y-%m-%dT%H:%M:%S"))
    if REDACT:
        record = redact_deep(record)
    os.makedirs(os.path.dirname(SPAN_LOG), exist_ok=True)
    with open(SPAN_LOG, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return span


SEARCH_DESCRIPTION = """Search the Acme SDK documentation for ONE caller's SDK version and return the best-matching passages.

WHEN TO USE: how to do something, example code, default values, parameter tables. `kind` picks the corpus: "docs" (reference pages and changelog), "samples" (runnable code samples), or "upgrade" (the 2.x-to-3.0 migration guide and changelog: use it for removed, renamed or deprecated methods).
`sdk_version` is the CALLER'S version, e.g. "2.4" or "3.0". Pass it on every call. Results are filtered to pages that exist in that version, and a page written for another version is never returned.
WHEN NOT TO USE: to check whether one name exists in a version (use the symbol check), or when something was deprecated or removed (use the changelog lookup).
IF YOU GET AN ERROR: it starts with a KIND. VERSION_REQUIRED means you left out sdk_version: resolve it and call again. UNSUPPORTED_VERSION means that version has no docs."""

DEPRECATION_DESCRIPTION = """Changelog lookup for ONE method, class or argument (for example "Client.sendMessage" or "AuthConfig.token"): when it was introduced, deprecated and removed, and what replaces it (and since which version the replacement exists).
WHEN TO USE: the question mentions a name that may be deprecated or renamed, or the answer would use one. Also returns the deprecation notice to show the caller.
WHEN NOT TO USE: for how-to or example code (use the doc search) or just to check a name exists (use the symbol check).
`sdk_version` is the caller's version; pass it every time."""

SYMBOL_DESCRIPTION = """Symbol check: does ONE named method, class or argument exist in ONE SDK version? Returns exactly one of current, deprecated, removed, not_yet or unknown, plus the nearest real names when it is not current.
WHEN TO USE: before telling anyone to call a method, and whenever the question names one ("does client.query() exist?"). `unknown` means no release of the SDK has ever had it: say so plainly and never invent a signature.
`sdk_version` is the version to check; pass it every time."""


@mcp.tool(description=SEARCH_DESCRIPTION)
def search_docs(query: str, sdk_version: str | None = None, kind: str = "docs", top_k: int = 3,
                trace_id: str = "", parent_span_id: str = "") -> str:
    t0 = time.perf_counter()
    received = {"query": query, "sdk_version": sdk_version, "kind": kind, "top_k": top_k}
    try:
        v = _version_arg(sdk_version, "search_docs")
    except ToolError:
        _log_span("search_docs", t0, trace_id, parent_span_id, received, {"error": "version"})
        raise
    if kind not in KIND_TO_TYPES:
        raise ToolError(f"BAD_KIND: kind must be one of {sorted(KIND_TO_TYPES)}, got {kind!r}")
    index = ix.get_index()
    try:
        results, info = index.search(query, v, top_k=max(1, min(int(top_k), 8)), mode="lenient" if POLICY == "lenient" else "strict",
                                     minor_filter=MINOR_FILTER, page_types=KIND_TO_TYPES[kind])
    except ix.VersionLeak as e:
        _log_span("search_docs", t0, trace_id, parent_span_id, received, {"error": "version_leak"})
        raise ToolError(f"VERSION_LEAK: {e}")
    span = _log_span("search_docs", t0, trace_id, parent_span_id, received,
                     {"results": len(results), "scope": info["scope"], "version_applied": fmt(v) if v else None})
    return json.dumps({"query": query, "version_requested": sdk_version, "version_applied": fmt(v) if v else None,
                       "scope": info["scope"], "kind": kind, "so_bridge": info["so_bridge"],
                       "prefix_expansion": info["prefix_expansion"],
                       "results": [ix.chunk_record(r) for r in results], "_server_span": span})


@mcp.tool(description=DEPRECATION_DESCRIPTION)
def lookup_deprecation(symbol: str, sdk_version: str | None = None, trace_id: str = "", parent_span_id: str = "") -> str:
    t0 = time.perf_counter()
    received = {"symbol": symbol, "sdk_version": sdk_version}
    try:
        v = _version_arg(sdk_version, "lookup_deprecation")
    except ToolError:
        _log_span("lookup_deprecation", t0, trace_id, parent_span_id, received, {"error": "version"})
        raise
    rec = sym.record(symbol, fmt(v) if v else None)
    if rec.get("deprecated"):
        dep = sym.parse_exact_version(rec["deprecated"])
        rec["deprecated_source"] = {"label": f"CHANGELOG {rec['deprecated']}.0 (Acme SDK 2.x)",
                                    "url": f"{ix.DOCS_HOST}/2.x/changelog#{rec['deprecated'].replace('.', '-')}-0", "version": f"2.{dep[1]}" if dep else None}
    if rec.get("removed"):
        rec["removed_source"] = {"label": f"CHANGELOG {rec['removed']}.0 (Acme SDK 3.0)",
                                 "url": f"{ix.DOCS_HOST}/3.0/changelog#{rec['removed'].replace('.', '-')}-0"}
    span = _log_span("lookup_deprecation", t0, trace_id, parent_span_id, received, {"status": rec.get("status")})
    rec["_server_span"] = span
    return json.dumps(rec)


@mcp.tool(description=SYMBOL_DESCRIPTION)
def symbol_exists(symbol: str, sdk_version: str | None = None, trace_id: str = "", parent_span_id: str = "") -> str:
    t0 = time.perf_counter()
    received = {"symbol": symbol, "sdk_version": sdk_version}
    try:
        v = _version_arg(sdk_version, "symbol_exists")
    except ToolError:
        _log_span("symbol_exists", t0, trace_id, parent_span_id, received, {"error": "version"})
        raise
    v = v or (3, 0)     # lenient mode only: 'latest' (this IS the Week-11 bug, kept so it can be measured)
    st = sym.status(symbol, v)
    nearest = []
    if st in ("unknown", "removed", "not_yet"):
        pool = [sid for sid in sym.manifest()[1] if sym.exists(sid, v) and sym.lifecycle(sid).get("kind") == "method" and sid != "Poller.next"]
        nearest = difflib.get_close_matches(symbol, pool, n=3, cutoff=0.35)
    span = _log_span("symbol_exists", t0, trace_id, parent_span_id, received, {"status": st})
    return json.dumps({"symbol": symbol, "version": fmt(v), "status": st, "exists": st in ("current", "deprecated"),
                       "status_in_3_0": sym.status(symbol, (3, 0)), "nearest": nearest,
                       "record": sym.record(symbol, fmt(v)), "_server_span": span})


if __name__ == "__main__":
    mcp.run()
