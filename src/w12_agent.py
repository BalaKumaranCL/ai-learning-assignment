"""Week 12: the hand-built agent loop (Week 7's plan -> act -> observe ->
repeat, still no framework), now running against the integrated retriever
with FOUR tools:

  * three that live behind the MCP server and are DISCOVERED AT RUNTIME --
    version-scoped doc search, changelog/deprecation lookup, symbol-exists check
  * one local tool -- verify a code sample (parse + imports + symbols + run)

THIS FILE KNOWS NO MCP TOOL NAMES (tests grep for them). The planner thinks in
NEEDS ("I need a doc search", "I need a lifecycle lookup", "I need an
existence check") and `pick_tool` matches each need to whichever discovered
tool's name + description fits; arguments are filled from each tool's own
input schema. Add a tool to the server and nothing here changes.

The planner is a deterministic stand-in for a tool-calling model (see
w12_llm.py): the rules in `plan_next` are the whole "reasoning", written down
so a trajectory eval can check them. Each lap is charged as one modelled model
call over the whole transcript so far (tokens are summed lap over lap), and
independent calls inside one lap run in parallel, as a tool-calling model does.
"""

import asyncio
import json
import re

import w12_codecheck as cc
from w12_text import GENERIC, stems, strip_parens
from w12_llm import SYSTEM_PROMPT, model_call
from w12_mcp import parse_result

MAX_LAPS = 12
MAX_NAMED = 2          # symbols named in the question that get an existence check
MAX_SWEEP = 4          # symbols found in the chosen sample/docs that get a lifecycle lookup
MAX_VERIFY = 3

# What each NEED looks like in a tool's name / description (stems, so wording can drift).
NEED_STEMS = {"search": ("searc", "docum"), "exists": ("symbo", "exist"), "lifecycle": ("depre", "chang", "looku")}

_STATUS_RE = re.compile(r"\b(still\s+(work|exist|supported|available)|no longer|exists?\b|is\s+\S+\s+(deprecated|removed|supported)|"
                        r"(was|been|got|is|are)\s+(removed|deprecated|renamed)|deprecated|removed|gone)\b", re.I)
_MIGRATION_RE = re.compile(r"\b(migrat\w*|upgrad\w*|move\s+to|switch\s+to|port\w*|replac\w*|renam\w*)\b", re.I)
_FACTUAL_RE = re.compile(r"\b(what('s|\s+is|\s+are)|which|default|value|type|required|raises?|returns?|how\s+(long|many|much))\b", re.I)
_HOWTO_RE = re.compile(r"\bhow\s+(do|can|should|would|to)\b", re.I)
_FILLER = {"acme", "what", "which", "when", "does", "this", "that", "with", "have", "from", "your", "about", "still", "work", "works", "there", "where",
           "would", "could", "should", "just", "also", "need", "want", "stuck", "getting", "keeps", "returning", "tried", "trying", "please", "help"}


def classify_intent(question, named):
    if named and _STATUS_RE.search(question):
        return "status"
    if _MIGRATION_RE.search(question):
        return "migration"
    if _FACTUAL_RE.search(question) and not _HOWTO_RE.search(question):
        return "factual"
    return "howto_code"


def pick_tool(need, tools):
    """Best discovered tool for a need, by stems in its name (weight 3) and first sentence (weight 1)."""
    best, best_score = None, 0
    for t in tools:
        name = t["name"].lower()
        first = re.split(r"(?<=[.!?:])\s", (t.get("description") or "").strip(), maxsplit=1)[0].lower()
        score = sum(3 for s in NEED_STEMS[need] if s in name) + sum(1 for s in NEED_STEMS[need] if s in first)
        if score > best_score:
            best, best_score = t, score
    return best


def fill_args(tool, slots):
    """Fill a tool's arguments from its OWN input schema: only properties it declares, only values we have."""
    args = {}
    for prop in (tool.get("inputSchema") or {}).get("properties", {}):
        key = {"sdk_version": "version", "version": "version", "api_version": "version"}.get(prop, prop)
        if slots.get(key) is not None:
            args[prop] = slots[key]
    return args


class State:
    def __init__(self, ctx):
        self.__dict__.update(ctx)
        self.done = set()
        self.exists, self.lifecycle = {}, {}
        self.docs, self.samples, self.upgrade = [], [], []
        self.chosen, self.rejected, self.verify_tried = None, [], 0
        self.transcript = []
        self.searches = []

    def removed_or_unknown(self):
        return [n for n in self.named if (self.exists.get(n["id"]) or {}).get("status") in ("removed", "unknown", "not_yet") or n["status_kind"] == "unknown"]

    def wants_code(self):
        # no sample for a method that never existed: a sample for something ELSE would answer a question nobody asked
        unknown = any((self.exists.get(n["id"]) or {}).get("status") == "unknown" or n["status_kind"] == "unknown" for n in self.named)
        return self.intent != "factual" and not unknown

    def search_query(self):
        for n in self.named:
            ex = self.exists.get(n["id"]) or {}
            rec = self.lifecycle.get(n["id"]) or ex.get("record") or {}
            if ex.get("status") == "removed" and rec.get("replacement"):
                return rec["replacement"].split(".")[-1]          # just the new name: the old name's words would drag the search back to it
            if (ex.get("status") == "unknown" or n["status_kind"] == "unknown") and ex.get("nearest"):
                return ex["nearest"][0].split(".")[-1]
        return self.outbound_q

    def _stems(self, text):
        return stems(text, _FILLER)

    def _question_stems(self):
        return self._stems(self.question)

    def _topic_terms(self):
        """What the question is ABOUT: its own content words, the name we searched for instead (a removed method's
        replacement), and the words the Stack Overflow bridge added for a colloquial phrasing -- all stemmed the way the index stems."""
        extra = " ".join(b.get("expansion", "") for s in self.searches for b in [s.get("so_bridge") or {}])
        return self._question_stems() | self._stems(self.search_query()) | self._stems(extra)

    def _relevance(self, chunk):
        """Overlap between the topic terms and the chunk's TITLE (its breadcrumb with the version label stripped, plus a sample's
        tags). Comparing with the body counted generic words: "request" in a print() string made a timeout sample 'relevant'
        to a headers question."""
        tags = re.search(r"^Tags: (.*)$", chunk["text"], re.M)
        terms = self._topic_terms()
        return len(terms & self._stems(strip_parens(chunk["anchor"]))) + len((terms - GENERIC) & self._stems(tags.group(1) if tags else ""))

    def candidates(self):
        """Code candidates: the most RELEVANT to the question first (samples win ties) -- rank alone put a send sample first for an auth question."""
        out = []
        for pool in (self.samples, self.docs):
            for c in pool:
                if "```python" in c["text"] and c["chunk_id"] not in {x["chunk_id"] for x in out}:
                    out.append(c)
        # a question ABOUT a removed / deprecated name must be answered with the replacement's sample, never with a sample of the old name
        about = {n["id"] for n in self.named if (self.exists.get(n["id"]) or {}).get("status") in ("removed", "deprecated")}
        out = [c for c in out if not (about & set(c.get("symbols", [])))] or out
        if self.config.relevance_floor and self._topic_terms():
            out = [c for c in out if self._relevance(c) >= 1]     # valid code about the WRONG thing is still a wrong answer
        return sorted(out, key=lambda c: (-self._relevance(c), 0 if c["page_type"] == "sample" else 1))

    def sweep_candidates(self):
        """Names the answer is about to use: the chosen sample first, then every top doc passage. The lifecycle
        lookup says which of them are deprecated, which are removed, and what each one REPLACED."""
        pool = []
        for c in ([self.chosen] if self.chosen else self.candidates()[:1]) + [d for d in self.docs[:3] if self._relevance(d) >= 1]:
            for sid in c.get("symbols", []):
                if "." in sid and sid not in pool:
                    pool.append(sid)
        return pool


def plan_next(st):
    """-> a list of steps for ONE lap. Several 'call' steps in a list are independent and run in parallel
    (a tool-calling model batches them in one turn); verify / pick / final are always alone."""
    cfg = st.config
    # 1. does each name the question uses exist in the version being asked about?  (all at once)
    todo = [{"type": "call", "need": "exists", "symbol": n["id"], "version": st.check_version, "key": ("exists", n["id"])}
            for n in st.named[:MAX_NAMED] if ("exists", n["id"]) not in st.done]
    if todo:
        return todo
    # 2. lifecycle (deprecated / removed / replaced-by) for every named name that is a real symbol
    todo = [{"type": "call", "need": "lifecycle", "symbol": n["id"], "version": st.scope, "key": ("lifecycle", n["id"])}
            for n in st.named[:MAX_NAMED]
            if st.exists.get(n["id"]) and st.exists[n["id"]]["status"] != "unknown" and ("lifecycle", n["id"]) not in st.done]
    if todo:
        return todo
    # 3. the searches (independent of each other, so one lap): upgrade info, samples, docs
    gone = st.removed_or_unknown()
    todo = []
    real_gone = [n for n in st.named if (st.exists.get(n["id"]) or {}).get("status") in ("removed", "deprecated", "not_yet")]
    if (st.intent == "migration" or real_gone) and "upgrade" not in st.done:
        todo.append({"type": "call", "need": "search", "kind": "upgrade", "query": st.search_query(), "version": st.scope, "top_k": 3, "key": "upgrade"})
    if st.wants_code() and "samples" not in st.done:
        todo.append({"type": "call", "need": "search", "kind": "samples", "query": st.search_query(), "version": st.scope, "top_k": 3, "key": "samples"})
    if "docs" not in st.done:
        todo.append({"type": "call", "need": "search", "kind": "docs", "query": st.search_query(), "version": st.scope, "top_k": 3, "key": "docs"})
    if todo:
        return todo
    # 4. choose the code sample -- verified when the gate is on
    if st.wants_code() and st.chosen is None and st.candidates():
        if not cfg.code_gate:
            return [{"type": "pick_unverified"}]
        pending = [c for c in st.candidates() if c["chunk_id"] not in {r["chunk_id"] for r in st.rejected}]
        if pending and st.verify_tried < MAX_VERIFY:
            return [{"type": "verify", "chunk": pending[0]}]
    # 5. lifecycle sweep over every name the answer is about to use (the unasked-deprecation net)
    todo = [{"type": "call", "need": "lifecycle", "symbol": sid, "version": st.scope, "key": ("lifecycle", sid)}
            for sid in st.sweep_candidates()[:MAX_SWEEP] if ("lifecycle", sid) not in st.done]
    if todo:
        return todo
    return [{"type": "final"}]


def _observation(text, limit=900):
    return text if len(text) <= limit else text[:limit] + " ...[truncated]"


async def _mcp_call(step, st, host, trace, lap_span, lap):
    """One MCP tool call (with the recoverable-error retry). -> (step, tool, data_or_text, ok, args, retried)"""
    cfg = st.config
    tool = pick_tool(step["need"], host.tools)
    if tool is None:
        return step, None, None, False, {}, False
    slots = {"query": step.get("query"), "symbol": step.get("symbol"), "kind": step.get("kind"), "top_k": step.get("top_k"),
             # Week 9's host only knew a version if the QUESTION TEXT said one (seam S3); `inject_version` is the fix
             "version": step["version"] if cfg.inject_version else st.mentioned_version}
    client_span_id = trace.next_span_id()
    if cfg.trace_hop:
        slots["trace_id"], slots["parent_span_id"] = trace.trace_id, client_span_id
    args = fill_args(tool, slots)
    text, is_err, ms = await host.call(tool["name"], args)
    retried = False
    if is_err and "VERSION_REQUIRED" in text and step["version"]:
        # recoverable error: the server says exactly what is missing, and the engine has it
        trace.add(f"tool:{tool['name']}", "tool", parent=lap_span["span_id"], latency_ms=ms, span_id=client_span_id, lap=lap,
                  tool=tool["name"], need=step["need"], error="VERSION_REQUIRED", args=args)
        client_span_id = trace.next_span_id()
        slots["version"] = step["version"]
        if cfg.trace_hop:
            slots["parent_span_id"] = client_span_id
        args = fill_args(tool, slots)
        text, is_err, ms = await host.call(tool["name"], args)
        retried = True
    data = None if is_err else parse_result(text)
    trace.add(f"tool:{tool['name']}", "tool", parent=lap_span["span_id"], latency_ms=ms, span_id=client_span_id, lap=lap,
              tool=tool["name"], need=step["need"], args=args, is_error=is_err, retried=retried)
    if data and "_server_span" in data:
        trace.merge_server_span(data.pop("_server_span"), parent=client_span_id)
    return step, tool, (data if data is not None else text), (not is_err and data is not None), args, retried


async def run_agent(ctx, host, trace, parent):
    """ctx: question, outbound_q, intent, named, scope, target, check_version, config, mentioned_version.
    -> (State, tool_calls)"""
    st = State(ctx)
    cfg = st.config
    calls = []

    for lap in range(1, MAX_LAPS + 1):
        steps = plan_next(st)
        history = "\n".join([SYSTEM_PROMPT, f"Q: {st.outbound_q}"] + st.transcript)
        descs = []
        for step in steps:
            if step["type"] == "call":
                shown = {k: v for k, v in step.items() if k not in ("type", "key", "need")}
                descs.append(f"CALL {step['need']}({shown})")
            else:
                descs.append({"verify": "CALL verify_sample(chunk)", "pick_unverified": "CHOOSE first candidate", "final": "FINAL ANSWER"}[step["type"]])
        lap_span = model_call(trace, f"plan:lap{lap}", "plan", parent, history, "\n".join(descs), f"plan{lap}")

        kind = steps[0]["type"]
        if kind == "final":
            break

        if kind == "pick_unverified":
            st.chosen = st.candidates()[0]
            st.transcript += [descs[0], "OBSERVATION: used the top candidate as retrieved (no verification step)"]
            continue

        if kind == "verify":
            chunk = steps[0]["chunk"]
            with trace.span("tool:verify_sample", "gate", parent=lap_span["span_id"], local=True) as sp:
                res = cc.check_markdown(chunk["text"], st.scope)
                sp["ok"], sp["problems"] = res["ok"], [p["detail"] for p in res["problems"]][:3]
            st.verify_tried += 1
            calls.append({"need": "verify", "tool": "verify_sample", "ok": res["ok"], "lap": lap})
            if res["ok"]:
                st.chosen = chunk
                st.transcript += [descs[0], f"OBSERVATION[verify]: {chunk['chunk_id']} parses, imports resolve, symbols exist in {st.scope}, runs"]
            else:
                st.rejected.append({"chunk_id": chunk["chunk_id"], "problems": [p["detail"] for p in res["problems"]][:3]})
                st.transcript += [descs[0], f"OBSERVATION[verify]: REJECTED {chunk['chunk_id']}: {res['problems'][0]['detail']}"]
            continue

        # a lap of independent MCP calls, run in parallel
        outs = await asyncio.gather(*[_mcp_call(step, st, host, trace, lap_span, lap) for step in steps])
        st.transcript += descs
        for step, tool, data, ok, args, retried in outs:
            st.done.add(step["key"])
            if tool is None:
                calls.append({"need": step["need"], "tool": None, "ok": False, "lap": lap})
                st.transcript.append(f"OBSERVATION: no discovered tool can {step['need']}")
                continue
            calls.append({"need": step["need"], "tool": tool["name"], "ok": ok, "args": args, "retried": retried, "lap": lap})
            st.transcript.append(f"OBSERVATION[{tool['name']}]: " + _observation(data if isinstance(data, str) else json.dumps(data)))
            if not ok:
                continue
            if step["need"] == "exists":
                st.exists[step["symbol"]] = data
            elif step["need"] == "lifecycle":
                st.lifecycle[step["symbol"]] = data
            else:
                results = data.get("results", [])
                setattr(st, step["kind"], results)
                st.searches.append({"kind": step["kind"], "so_bridge": data.get("so_bridge"), "prefix_expansion": data.get("prefix_expansion"),
                                    "scope": data.get("scope"), "version_applied": data.get("version_applied")})
    return st, calls
