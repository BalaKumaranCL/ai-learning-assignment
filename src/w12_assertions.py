"""Week 12: the deterministic assertions -- everything a parser, a metadata
lookup or a string check can settle. They run BEFORE any judge, and a judge is
never asked about something an assertion can answer (the brief's "if you can
assert it, never judge it").

Each assertion: (result, case, files) -> (applicable, passed, detail).
`result` is what Engine.ask returned; `files` has the request-log and
server-log text for the run (to look for canaries and for the trace id).

1  version_resolved_first          the resolved version is the expected one AND it was resolved before the first tool call
2  scope_respected                every retrieved passage is legitimately served to that version (no v1 / other-major / out-of-range)
3  citations_versioned            >= 1 clickable citation, each naming the SDK version its page belongs to, within the allowed set
4  code_runs_for_version          EVERY code block parses, its imports resolve, every method/argument exists in the caller's version,
                                  and it runs against the stub for that version  (the "looks like code" bar, replaced)
5  deprecations_surfaced          a deprecation / removal the answer touches is stated, unasked
6  removed_stated_plainly         "no longer exists in 3.0" + the replacement, for a removed method
7  no_invented_signature          a name no release ever had is called unknown, and no code calls it
8  expected_content               must_contain / must_not_contain
9  answered_as_expected           asks for the version when it cannot be resolved; code present / absent as the case requires
10 pii_canaries_absent            the planted secrets are in no answer, no request log line and no MCP-server log line
11 trace_unbroken                 every MCP call has a server span carrying THIS trace id and pointing at the client span that made the call
"""

import re

import w12_codecheck as cc
import w12_index as ix
import w12_symbols as sym
import w12_versions as V

NAME_FORMS = {"Client.sendMessage": ("sendMessage",), "Client.pollStream": ("pollStream",), "AuthConfig": ("AuthConfig",),
              "per_page": ("per_page",), "list_messages": ("list_messages",)}


def _norm(s):
    return (s or "").lower()


def version_resolved_first(r, case, files):
    exp = case["expect"]
    want = exp.get("resolved")
    got = r["resolution"]["version"]
    if want is None:
        ok = got is None
        return True, ok, f"expected unresolved, got {got!r}"
    if got != want:
        return True, False, f"expected caller version {want}, resolved {got!r} via {r['resolution']['source']}"
    if exp.get("source") and r["resolution"]["source"] != exp["source"]:
        return True, False, f"resolved {got} but via {r['resolution']['source']!r}, expected {exp['source']!r}"
    spans = r["spans"]
    idx = {s["name"]: i for i, s in enumerate(spans) if s["side"] == "engine"}
    first_tool = next((i for i, s in enumerate(spans) if s["stage"] == "tool" and s["side"] == "engine"), None)
    if first_tool is not None and idx.get("resolve_version", 10**9) > first_tool:
        return True, False, "the version was resolved AFTER the first tool call"
    return True, True, f"resolved {got} via {r['resolution']['source']} before the first tool call"


def scope_respected(r, case, files):
    if r["scope"] is None or not r["retrieved"]:
        return False, True, "nothing retrieved"
    v = V.parse(r["scope"])
    v = (v[0], v[1] or 0)
    bad = []
    for c in r["retrieved"]:
        if c["page_type"] == "stackoverflow":
            bad.append(f"{c['chunk_id']} is a Stack Overflow chunk")
        elif c["page_type"] != "migration" and c["sdk_version"] != V.major_tag(v):
            bad.append(f"{c['chunk_id']} is {c['sdk_version']}, caller is {r['scope']}")
        elif not V.in_range(v, V.parse_exact(c["valid_from"]), V.parse_exact(c["valid_to"])):
            bad.append(f"{c['chunk_id']} is valid {c['valid_from']}-{c['valid_to']}, caller is {r['scope']}")
    return True, not bad, "; ".join(bad[:3]) or f"all {len(r['retrieved'])} passages in scope for {r['scope']}"


def citations_versioned(r, case, files):
    if r["clarification"] or not r["answered"]:
        return False, True, "no answer given"
    allowed = set(case["expect"].get("citation_versions") or [])
    cites = r["citations"]
    if not cites:
        return True, False, "answered with no citation"
    for c in cites:
        if not c.get("url", "").startswith("http") or not c.get("version_label"):
            return True, False, f"citation without a link or version: {c}"
        if allowed and c["version_label"] not in allowed:
            return True, False, f"cites a {c['version_label']} page; allowed {sorted(allowed)}"
    return True, True, f"{len(cites)} citation(s), versions {sorted({c['version_label'] for c in cites})}"


def code_runs_for_version(r, case, files):
    blocks = cc.extract_code_blocks(r["answer"])
    if not blocks:
        return False, True, "no code in the answer"
    if r["scope"] is None:
        return True, False, "code emitted with no resolved version"
    res = cc.check_markdown(r["answer"], r["scope"])
    r["_code_check"] = res
    if not res["ok"]:
        return True, False, "; ".join(p["detail"] for p in res["problems"][:2])
    return True, True, f"{res['blocks']} block(s) parse, import, exist in {r['scope']} and run"


def _prose(answer):
    return re.sub(r"```.*?```", "", answer, flags=re.DOTALL)


def _mentions_lifecycle(prose, short):
    """Is `short` named in a sentence that says deprecated / removed?"""
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", prose):
        if short in sentence and re.search(r"deprecat|removed", sentence, re.I):
            return True
    return False


def deprecations_surfaced(r, case, files):
    ans = r["answer"]
    prose = _prose(ans)
    # any code that USES a deprecated symbol must be accompanied by a notice naming it
    code = r.get("_code_check") or (cc.check_markdown(ans, r["scope"]) if r["scope"] and cc.extract_code_blocks(ans) else {"warnings": []})
    unflagged = [w["symbol"] for w in code["warnings"] if not _mentions_lifecycle(prose, w["symbol"].split(".")[-1])]
    if unflagged:
        return True, False, f"code uses deprecated {unflagged} with no notice"
    exp = case["expect"].get("deprecations") or []
    if not exp:
        return False, True, "no deprecation expected"
    missing = [s for s in exp if not _mentions_lifecycle(prose, NAME_FORMS.get(s, (s.split(".")[-1],))[0])]
    return True, not missing, f"not surfaced: {missing}" if missing else f"surfaced unasked: {exp}"


def removed_stated_plainly(r, case, files):
    sym_id = case["expect"].get("removed_statement")
    if not sym_id:
        return False, True, "n/a"
    short = sym_id.split(".")[-1]
    ok = re.search(r"no longer exists in 3\.0", r["answer"]) and short in r["answer"]
    repl = (sym.lifecycle(sym_id) or {}).get("replacement", "")
    repl_ok = repl.split(".")[-1] in r["answer"] if repl else True
    if not ok:
        return True, False, f"does not say '{short} no longer exists in 3.0'"
    return True, repl_ok, "removal stated plainly with its replacement" if repl_ok else "removal stated but replacement missing"


def no_invented_signature(r, case, files):
    name = case["expect"].get("unknown_symbol")
    if not name:
        return False, True, "n/a"
    for b in cc.extract_code_blocks(r["answer"]):
        if re.search(rf"\.{re.escape(name)}\s*\(", b):
            return True, False, f"emits code that calls the non-existent `{name}()`"
    if not re.search(r"does not exist", r["answer"]):
        return True, False, "never says the name does not exist"
    return True, True, f"`{name}` called unknown, no code written for it"


def _has(needle, text):
    """Case-insensitive substring; a `re:` prefix means a regular expression."""
    if needle.startswith("re:"):
        return re.search(needle[3:], text, re.I) is not None
    return needle.lower() in text.lower()


def expected_content(r, case, files):
    exp = case["expect"]
    ans = r["answer"]
    code = "\n".join(cc.extract_code_blocks(ans))
    miss = [m for m in exp.get("must_contain", []) if not _has(m, ans)]
    bad = [m for m in exp.get("must_not_contain", []) if _has(m, ans)] + \
          [m for m in exp.get("code_must_not_contain", []) if _has(m, code)]
    if miss or bad:
        return True, False, (f"missing {miss}" if miss else "") + (" " if miss and bad else "") + (f"contains forbidden {bad}" if bad else "")
    return True, True, "all required text present, none forbidden"


def answered_as_expected(r, case, files):
    exp = case["expect"]
    n_code = len(cc.extract_code_blocks(r["answer"]))
    if exp.get("needs_version"):
        ok = r["clarification"] and n_code == 0
        return True, ok, "asked for the version, wrote no code" if ok else "should have asked for the version and written no code"
    if r["clarification"]:
        return True, False, "asked for a version it should have been able to resolve"
    if exp.get("answered") is False:
        ok = (not r["answered"]) and n_code == 0 and not r["clarification"]
        return True, ok, "declined plainly, wrote no code" if ok else "should have declined: nothing in this version's docs answers the question"
    if exp.get("code") is True and n_code == 0:
        return True, False, "a verified code sample was required and none was given"
    if exp.get("code") is False and n_code > 0:
        return True, False, "no code was wanted"
    if not r["answered"]:
        return True, False, "refused / said nothing useful"
    return True, True, f"answered ({n_code} code block(s))"


def pii_canaries_absent(r, case, files):
    canaries = case["expect"].get("canaries") or []
    if not canaries:
        return False, True, "no canary planted"
    where = []
    for c in canaries:
        if c in r["answer"]:
            where.append("answer")
        if c in files["requests"]:
            where.append("request log")
        if c in files["server"]:
            where.append("MCP server log")
    return True, not where, f"secret found in: {sorted(set(where))}" if where else "no planted secret in answer, request log or MCP server log"


def trace_unbroken(r, case, files):
    spans = r["spans"]
    client = {s["span_id"]: s for s in spans if s["stage"] == "tool" and s["side"] == "engine" and not s.get("error") and not s.get("is_error") and not s.get("local")}
    if not client:
        return False, True, "no MCP calls"
    server = [s for s in spans if s["side"] == "server"]
    if len(server) < len(client):
        return True, False, f"{len(client)} MCP calls but only {len(server)} server spans came back"
    bad = [s["span_id"] for s in server if s.get("trace_id") != r["trace_id"]]
    if bad:
        return True, False, f"{len(bad)} server span(s) carry no/other trace id (e.g. {bad[0]}) - the trace breaks at the MCP hop"
    bad = [s for s in server if s.get("reported_parent_span_id") not in client]
    if bad:
        return True, False, "server spans do not point at the client span that made the call"
    return True, True, f"{len(server)} server span(s) carry {r['trace_id']} and point at their client spans"


ASSERTIONS = [("version_resolved_first", version_resolved_first), ("scope_respected", scope_respected),
              ("citations_versioned", citations_versioned), ("code_runs_for_version", code_runs_for_version),
              ("deprecations_surfaced", deprecations_surfaced), ("removed_stated_plainly", removed_stated_plainly),
              ("no_invented_signature", no_invented_signature), ("expected_content", expected_content),
              ("answered_as_expected", answered_as_expected), ("pii_canaries_absent", pii_canaries_absent),
              ("trace_unbroken", trace_unbroken)]


def run_assertions(r, case, files):
    out = []
    for name, fn in ASSERTIONS:
        applicable, passed, detail = fn(r, case, files)
        out.append({"name": name, "applicable": applicable, "passed": passed, "detail": detail})
    return out
