"""Week 12: the Week-6 eval suite, running against the INTEGRATED system in one
call (`run_suite`), plus the error-taxonomy re-score (Week 5) over its results.

A case PASSES when every applicable deterministic assertion passes (w12_assertions)
AND -- only then, "assertions before judges" -- the judge says Y. A case marked
`xfail` in the case file is a documented limit: it is reported as XFAIL when it
fails (and as XPASS, loudly, if it ever passes) and never counted as a pass.

Taxonomy (Week 5 style: named modes, frequency, severity, one trace id each).
A case can show more than one mode, so frequencies are "cases showing the mode /
n", not a partition. Modes marked NEW exist only because components were joined.
"""

import json
import os

import w12_assertions as A
import w12_codecheck as cc
from w12_engine import Config, run_batch_sync
from w12_judge import judge_w12

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CASES_PATH = os.path.join(BASE_DIR, "data", "w12", "eval_cases.json")

MODES = [
    # name, NEW-by-integration?, severity, one-line meaning
    ("wrong_version_answer", False, "Ships code that fails at runtime in the caller's app", "the code (or the page it came from) does not belong to the caller's version"),
    ("version_dropped_at_hop", True, "Ships code that fails at runtime in the caller's app (root cause of the above)", "the resolved version never reached the MCP server, so it searched every version"),
    ("trace_lost_at_hop", True, "Blind spot: the request cannot be debugged end to end", "the server's spans do not carry the request's trace id"),
    ("secret_in_server_log", True, "Security incident: a pasted key is on disk in a log nobody redacts", "a planted secret reached the MCP server's own log"),
    ("version_misresolved", False, "Ships code for the wrong version, with confidence", "the caller's version was resolved wrongly (or defaulted)"),
    ("lifecycle_not_surfaced", False, "Silent breakage later: the upgrade fails on something nobody warned about", "a deprecation / removal was not stated, or an invented signature was written"),
    ("answer_missing_the_fact", False, "Annoys: right version, wrong or empty answer", "a retrieval / composition miss: the fact the caller needed is not in the answer"),
]
MODE_META = {m[0]: m for m in MODES}


def load_cases():
    with open(CASES_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def detect_modes(r, case, asserts):
    failed = {a["name"] for a in asserts if a["applicable"] and not a["passed"]}
    detail = {a["name"]: a["detail"] for a in asserts}
    modes = []
    if "code_runs_for_version" in failed or ("scope_respected" in failed and "```python" in r["answer"]) or \
            ("citations_versioned" in failed and "cites a" in detail["citations_versioned"]):
        modes.append("wrong_version_answer")
    dropped = [c for c in r["tool_calls"] if c.get("need") == "search" and c.get("args") is not None
               and "sdk_version" not in c["args"] and not c.get("retried")]
    if r["scope"] and dropped:
        modes.append("version_dropped_at_hop")
    if "trace_unbroken" in failed:
        modes.append("trace_lost_at_hop")
    if "pii_canaries_absent" in failed and "MCP server log" in detail["pii_canaries_absent"]:
        modes.append("secret_in_server_log")
    if "version_resolved_first" in failed:
        modes.append("version_misresolved")
    if failed & {"deprecations_surfaced", "removed_stated_plainly", "no_invented_signature"}:
        modes.append("lifecycle_not_surfaced")
    if not modes and failed & {"expected_content", "answered_as_expected", "citations_versioned", "scope_respected"}:
        modes.append("answer_missing_the_fact")
    return modes


def run_suite(config, cases=None, run_dir=None, with_judge=True, guards=True):
    cases = cases or load_cases()
    reqs = [{"case_id": c["id"], "question": c["question"], "sdk_version": c["sdk_version"]} for c in cases]
    results, discovery = run_batch_sync(config, reqs, run_dir)
    run_dir = run_dir or os.path.join(BASE_DIR, "output", "w12", "runs", config.name)
    files = {"requests": _read(os.path.join(run_dir, "requests.jsonl")), "server": _read(os.path.join(run_dir, "mcp_server_spans.jsonl"))}

    rows = []
    for case, r in zip(cases, results):
        asserts = A.run_assertions(r, case, files)
        failed = [a for a in asserts if a["applicable"] and not a["passed"]]
        judge = None
        # assertions before judges; and a case whose RIGHT answer is a plain refusal is not judged (the Week 6 lesson:
        # the judge marks every refusal "not helpful", so it cannot tell a correct refusal from a bad one)
        if not failed and with_judge and case["expect"].get("answered") is not False:
            judge = judge_w12({"question": r["question"], "sdk_version_sent": r["sdk_version_sent"], "answer": r["answer"]})
        passed = not failed and (judge in (None, "Y"))
        xfail = case["expect"].get("xfail")
        status = ("XPASS" if passed else "XFAIL") if xfail else ("PASS" if passed else "FAIL")
        rows.append({"id": case["id"], "category": case["category"], "question": case["question"], "sdk_version": case["sdk_version"],
                     "status": status, "passed": passed, "xfail": xfail, "judge": judge,
                     "failures": [f"{a['name']}: {a['detail']}" for a in failed] + ([f"judge: N"] if judge == "N" else []),
                     "assertions": asserts, "modes": detect_modes(r, case, asserts) if not passed else [],
                     "trace_id": r["trace_id"], "scope": r["scope"], "resolution": r["resolution"], "answer": r["answer"],
                     "has_code": "```python" in r["answer"], "totals": r["totals"], "by_stage": r["by_stage"], "laps": r["laps"],
                     "tool_calls": r["tool_calls"], "result": r})
    if guards and cases is not None and len(cases) > 0:
        import w12_guards as G
        for gid, gname, fn in G.GUARDS:
            ok, detail = fn()
            rows.append({"id": gid, "category": "guard", "question": f"(no question - watches the corpus: {gname})", "sdk_version": None,
                         "status": "PASS" if ok else "FAIL", "passed": ok, "xfail": None, "judge": None,
                         "failures": [] if ok else [f"{gname}: {detail}"], "detail": detail,
                         "assertions": [{"name": gname, "applicable": True, "passed": ok, "detail": detail}],
                         "modes": [] if ok else ["lifecycle_not_surfaced"], "trace_id": "-", "scope": None, "resolution": {}, "answer": "",
                         "has_code": False, "totals": {"latency_ms": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0}, "by_stage": {},
                         "laps": 0, "tool_calls": [], "result": None})
    return {"config": config.name, "flags": config.flags(), "discovery": discovery, "rows": rows, "summary": summarize(rows)}


def summarize(rows):
    n = len(rows)
    counted = [r for r in rows if not r["xfail"]]
    code_rows = [r for r in rows if r["has_code"]]
    code_fail = [r for r in code_rows if any(a["name"] == "code_runs_for_version" and a["applicable"] and not a["passed"] for a in r["assertions"])]
    return {
        "n": n, "pass": sum(r["status"] == "PASS" for r in rows), "fail": sum(r["status"] == "FAIL" for r in rows),
        "xfail": sum(r["status"] == "XFAIL" for r in rows), "xpass": sum(r["status"] == "XPASS" for r in rows),
        "pass_rate_of_counted": round(sum(r["status"] == "PASS" for r in counted) / len(counted), 4) if counted else None,
        "answers_with_code": len(code_rows), "wrong_version_code": len(code_fail),
        "wrong_version_code_rate": round(len(code_fail) / len(code_rows), 4) if code_rows else None,
        "trace_broken": sum(1 for r in rows for a in r["assertions"] if a["name"] == "trace_unbroken" and a["applicable"] and not a["passed"]),
        "canary_leaks": sum(1 for r in rows for a in r["assertions"] if a["name"] == "pii_canaries_absent" and a["applicable"] and not a["passed"]),
        "canary_cases": sum(1 for r in rows for a in r["assertions"] if a["name"] == "pii_canaries_absent" and a["applicable"]),
        "misresolved": sum(1 for r in rows for a in r["assertions"] if a["name"] == "version_resolved_first" and a["applicable"] and not a["passed"]),
    }


def taxonomy(rows):
    """-> list of {mode, new, count, pct, severity, trace_id, case_id} for modes that occurred, most frequent first."""
    n = len(rows)
    out = []
    for name, new, severity, meaning in MODES:
        hit = [r for r in rows if name in r["modes"]]
        if hit:
            out.append({"mode": name, "new": new, "count": len(hit), "pct": round(100 * len(hit) / n, 1), "severity": severity,
                        "meaning": meaning, "trace_id": hit[0]["trace_id"], "case_id": hit[0]["id"], "cases": [r["id"] for r in hit]})
    out.sort(key=lambda m: -m["count"])
    return out


def old_bar(row):
    """The Week 6/11 acceptance bar, applied to an integrated answer: every code block PARSES, every cited page is of the
    caller's major version, nothing deprecated by the OLD four-name list is unflagged, and the judge says helpful.
    This is the 'looks like code' bar the bonus asks us to stop accepting."""
    import ast
    import deprecations
    r = row["result"]
    ans = r["answer"]
    if r["clarification"] or not r["answered"] or r["scope"] is None:
        return False
    try:
        for b in cc.extract_code_blocks(ans):
            ast.parse(b)
    except SyntaxError:
        return False
    major = r["scope"].split(".")[0]
    for c in r["citations"]:
        lab = c["version_label"]
        if c["page_type"] not in ("migration", "changelog") and not lab.startswith(major):
            return False
    if deprecations.unflagged_deprecated_symbols(ans, f"v{major}", True):
        return False
    return judge_w12({"question": r["question"], "sdk_version_sent": r["sdk_version_sent"], "answer": ans}) == "Y"


def parses_only_bar(row):
    """The bare 'looks like code' bar and nothing else: the answer has code and every block parses."""
    import ast
    r = row["result"]
    if r["clarification"] or not r["answered"]:
        return False
    try:
        for b in cc.extract_code_blocks(r["answer"]):
            ast.parse(b)
    except SyntaxError:
        return False
    return True


def looks_like_code_bar(row):
    """The weakest bar, the one the brief warns about: the answer contains code, every block PARSES, and a judge calls it helpful."""
    import ast
    r = row["result"]
    if r["clarification"] or not r["answered"]:
        return False
    try:
        for b in cc.extract_code_blocks(r["answer"]):
            ast.parse(b)
    except SyntaxError:
        return False
    return judge_w12({"question": r["question"], "sdk_version_sent": r["sdk_version_sent"], "answer": r["answer"]}) == "Y"


def bonus_execute_check(rows):
    """Of the answers that clear a bar and contain code, how many go red under parse + imports + symbols-exist-in-THIS-version + run?
    Three bars, weakest first: parses only; parses + the judge calls it helpful; the Week 6/11 'old bar' (parses, cited page of the caller's
    major, old deprecation list, judge). -> {'parses_only': {...}, 'looks_like_code': {...}, 'old_bar': {...}}"""
    out = {}
    for name, bar in (("parses_only", parses_only_bar), ("looks_like_code", looks_like_code_bar), ("old_bar", old_bar)):
        passing = [r for r in rows if r["has_code"] and bar(r)]
        went_red = []
        for r in passing:
            res = cc.check_markdown(r["answer"], r["scope"])
            if not res["ok"]:
                went_red.append({"id": r["id"], "trace_id": r["trace_id"], "why": res["problems"][0]["detail"]})
        out[name] = {"passing_with_code": len(passing), "went_red": len(went_red), "cases": went_red}
    return out
