"""Week 12 integration tests: the whole system through a LIVE MCP server (skipped when the `mcp` package is missing).
Units live in test_w12.py."""

import json
import os
import re

import pytest

pytest.importorskip("mcp")

import w12_codecheck as cc  # noqa: E402
import w12_engine as E  # noqa: E402
import w12_eval as EV  # noqa: E402
import w12_trajectory as T  # noqa: E402
from w12_judge import judge_w12  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _json(*parts):
    with open(os.path.join(BASE, *parts), "r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def fixed_suite(tmp_path_factory):
    return EV.run_suite(E.FIXED, run_dir=str(tmp_path_factory.mktemp("fixed")))


@pytest.fixture(scope="module")
def naive_suite(tmp_path_factory):
    return EV.run_suite(E.NAIVE, run_dir=str(tmp_path_factory.mktemp("naive")), with_judge=False)


def _row(suite, cid):
    return next(r for r in suite["rows"] if r["id"] == cid)


def test_the_fixed_system_has_no_unexpected_failure(fixed_suite):
    bad = [(r["id"], r["failures"]) for r in fixed_suite["rows"] if r["status"] in ("FAIL", "XPASS")]
    assert not bad, bad
    assert {r["id"] for r in fixed_suite["rows"] if r["status"] == "XFAIL"} == {"C07", "C34"}
    s = fixed_suite["summary"]
    assert s["wrong_version_code"] == 0 and s["trace_broken"] == 0 and s["canary_leaks"] == 0 and s["misresolved"] == 0


def test_mcp_tools_are_discovered_at_runtime(fixed_suite):
    assert set(fixed_suite["discovery"]["acme-sdk-docs"]) == {"search_docs", "lookup_deprecation", "symbol_exists"}


def test_a_2_4_caller_gets_2_4_code_with_versioned_citations_and_an_unasked_notice(fixed_suite):
    r = _row(fixed_suite, "C08")["result"]
    assert "page=page" in r["answer"] and "cursor=cursor" not in r["answer"]
    assert r["resolution"]["version"] == "2.4" and all(c["version_label"] == "2.x" for c in r["citations"])
    assert "removed in 3.0" in r["answer"]                                  # unasked


def test_the_version_is_resolved_before_the_first_tool_call(fixed_suite):
    spans = _row(fixed_suite, "C01")["result"]["spans"]
    names = [s["name"] for s in spans if s["side"] == "engine"]
    first_tool = next(i for i, s in enumerate(spans) if s["stage"] == "tool")
    assert names.index("resolve_version") < first_tool


def test_one_trace_id_survives_both_hops(fixed_suite):
    r = _row(fixed_suite, "C13")["result"]
    server = [s for s in r["spans"] if s["side"] == "server"]
    assert server and all(s["trace_id"] == r["trace_id"] for s in server)
    client_ids = {s["span_id"] for s in r["spans"] if s["stage"] == "tool" and s["side"] == "engine"}
    assert all(s["reported_parent_span_id"] in client_ids for s in server)


def test_pasted_secrets_are_on_disk_nowhere(fixed_suite, tmp_path_factory):
    for cid in ("C30", "C31", "C32"):
        assert _row(fixed_suite, cid)["status"] == "PASS"
    assert all(a["passed"] for r in fixed_suite["rows"] for a in r["assertions"] if a["name"] == "pii_canaries_absent")


def test_removed_method_is_said_plainly_and_unknown_is_never_invented(fixed_suite):
    gone = _row(fixed_suite, "C18")["answer"]
    assert "no longer exists in 3.0" in gone and "Client.stream" in gone and "pollStream(" not in cc.extract_code_blocks(gone)[0]
    unk = _row(fixed_suite, "C23")["answer"]
    assert "does not exist" in unk and "```" not in unk


def test_no_version_means_ask_and_no_tools(fixed_suite):
    r = _row(fixed_suite, "C05")["result"]
    assert r["clarification"] and r["tool_calls"] == [] and "```" not in r["answer"]


def test_the_first_wiring_reproduces_the_headline_failure(naive_suite):
    r = _row(naive_suite, "C01")["result"]       # "How do I send a message?" from a 2.4 caller
    code = cc.extract_code_blocks(r["answer"])[0]
    assert r["resolution"]["version"] == "2.4" and 'api_key="' in code and "Acme SDK 3.0" in r["answer"]    # 2.4 caller, 3.0 snippet, 3.0 citation
    assert not cc.check_code(code, "2.4")["ok"]                                                              # imports cleanly, fails in their app
    s = naive_suite["summary"]
    assert s["wrong_version_code"] >= 8 and s["trace_broken"] > 30 and s["canary_leaks"] == s["canary_cases"] == 3


def test_every_flag_matters_in_the_naive_system_only_together(naive_suite, fixed_suite):
    assert naive_suite["summary"]["pass"] <= 3 and fixed_suite["summary"]["fail"] == 0


def test_judge_agreement_with_hand_labels_clears_85(fixed_suite):
    labels = {l["id"]: l["label"] for l in _json("data", "w12", "hand_labels.json")["labels"]}
    rows = [r for r in fixed_suite["rows"] if r["category"] != "guard"]
    agree = sum(judge_w12({"question": r["question"], "sdk_version_sent": r["result"]["sdk_version_sent"], "answer": r["answer"]}) == labels[r["id"]] for r in rows)
    assert agree / len(rows) >= 0.85


def test_the_judge_is_never_asked_about_what_an_assertion_failed(fixed_suite, naive_suite):
    assert all(r["judge"] is None for r in naive_suite["rows"])
    assert _row(fixed_suite, "C36")["judge"] is None                    # an expected refusal is not judged


def test_trajectory_eval_reports_a_gap_and_the_numbers(fixed_suite):
    t = T.evaluate(fixed_suite["rows"])
    s = t["summary"]
    assert s["n"] >= 10 and 0 <= s["tool_choice_accuracy"] <= 1
    assert s["outcome_vs_trajectory_gap"] == round(s["outcome_pass_rate"] - s["trajectory_pass_rate"], 4)
    assert next(r for r in t["rows"] if r["id"] == "T08")["observed"] == []       # no version: no tools


def test_closed_loop_red_then_green_with_no_regression(tmp_path_factory):
    shipped = E.with_flags(E.FIXED, "shipped_before_fix", relevance_floor=False)
    red = EV.run_suite(shipped, run_dir=str(tmp_path_factory.mktemp("red")), with_judge=False)
    green = EV.run_suite(E.FIXED, run_dir=str(tmp_path_factory.mktemp("green")), with_judge=False)
    assert _row(red, "C36")["status"] == "FAIL" and _row(green, "C36")["status"] == "PASS"
    before = {r["id"]: r["status"] for r in red["rows"]}
    assert not [r["id"] for r in green["rows"] if before[r["id"]] == "PASS" and r["status"] != "PASS"]


def test_version_sweep_is_clean_on_the_fixed_system(tmp_path_factory):
    import w12_sweep as S
    results, _ = E.run_batch_sync(E.FIXED, S.sweep_requests(), run_dir=str(tmp_path_factory.mktemp("sweep")))
    bad, total = S.grade(results)
    assert total == 66 and not bad, bad[:2]


def test_a_client_that_is_not_ours_can_call_the_server():
    import subprocess
    import sys
    p = subprocess.run([sys.executable, os.path.join(BASE, "reviewer_client.py")], capture_output=True, text=True, encoding="utf-8", timeout=120, cwd=BASE)
    assert p.returncode == 0, p.stderr[-400:]
    assert "VERSION_REQUIRED" in p.stdout and "reviewer-trace-0001" in p.stdout and "**unknown**" in p.stdout and "**removed**" in p.stdout
    src = open(os.path.join(BASE, "reviewer_client.py"), encoding="utf-8").read()
    assert not re.search(r"^\s*(from|import) (w12_|src|agent_|mcp_agent)", src, re.M)     # imports nothing from this repo
