"""Week 10 tests -- plain Python, no MCP SDK needed. Latency/token VALUES are
not pinned (they follow the documented constants); structure and invariants are."""

import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))

import multi_agent  # noqa: E402
import w10_race as w  # noqa: E402

OUT = os.path.join(BASE, "output", "w10")


def _q(qid):
    return next(q for q in w.load_questions() if q["id"] == qid)


def test_race_uses_the_same_ten_cases_and_same_judge():
    race = w.run_race()
    assert [q["id"] for q in race["questions"]] == [f"Q{i}" for i in range(1, 11)]
    assert race["single_summary"]["n"] == race["multi_summary"]["n"] == 10


def test_ledger_tokens_equal_the_sum_of_llm_rows():
    r = w.run_multi(_q("Q1"), False)
    rows = [x for x in r["ledger"].rows if x["kind"] == "LLM"]
    assert r["total_tokens"] == sum(x["in_tokens"] + x["out_tokens"] for x in rows)
    assert r["model_calls"] == len(rows)
    assert sum(r["ledger"].bucket_tokens().values()) == r["total_tokens"]


def test_multiplier_and_bucket_shares_are_consistent():
    race = w.run_race()
    assert w.multiplier(race) == race["multi_summary"]["total_tokens"] / race["single_summary"]["total_tokens"]
    shares = w.bucket_shares(race)
    assert abs(sum(s for _, _, s in shares) - 1.0) < 1e-9
    assert shares[0][2] == max(s for _, _, s in shares)


def test_code_worker_has_narrow_tools_and_receives_exactly_one_handoff():
    r = w.run_multi(_q("Q6"), False)
    handoffs = [x for x in r["ledger"].rows if x["kind"] == "HANDOFF" and x["dst"] == "code-sample-worker"]
    assert len(handoffs) == 1
    assert "Do not check deprecation" in multi_agent.CODE_SYSTEM
    # minimal context: the hand-off is a short payload, not a resend of the reference docs
    assert handoffs[0]["payload_tokens"] < 120


def test_injected_500_is_retried_then_ships_unverified_answer_by_default():
    r = w.run_multi(_q("Q6"), False, version_worker_failures=99)
    assert r["version_attempts"] == 2 and not r["version_check_ok"] and not r["disclosed"]
    assert w.classify_failure(r).startswith("LIED")
    assert not r["pass"]


def test_disclosure_flag_degrades_honestly_and_transient_500_recovers():
    d = w.run_multi(_q("Q6"), False, version_worker_failures=99, disclose_failures=True)
    assert d["disclosed"] and w.classify_failure(d).startswith("DEGRADED")
    t = w.run_multi(_q("Q6"), False, version_worker_failures=1)
    assert t["version_check_ok"] and t["version_attempts"] == 2 and t["pass"]
    assert w.classify_failure(t).startswith("RETRIED")


def test_percentile_is_nearest_rank():
    assert w.percentile(list(range(1, 11)), 50) == 5
    assert w.percentile(list(range(1, 11)), 99) == 10


def test_deliverables_exist_and_verdict_meets_the_brief():
    for name in ("race_table.md", "handoffs.log", "failure_case.md", "verdict.md", "agent_card.json", "a2a_lifecycle.md"):
        assert os.path.exists(os.path.join(OUT, name)), name
    with open(os.path.join(OUT, "verdict.md"), encoding="utf-8") as fh:
        text = fh.read()
    assert len([ln for ln in text.splitlines() if ln.strip()]) <= 10
    assert "KILL" in text or "KEEP" in text
    assert "sunk" in text.lower()
    with open(os.path.join(OUT, "race_table.md"), encoding="utf-8") as fh:
        table = fh.read()
    assert "2.2x" in table and "2.2x" in text  # verdict cites numbers that are in the table


def test_agent_card_has_required_a2a_fields():
    with open(os.path.join(OUT, "agent_card.json"), encoding="utf-8") as fh:
        card = json.load(fh)
    for field in ("name", "description", "supportedInterfaces", "version", "capabilities", "defaultInputModes", "defaultOutputModes", "skills"):
        assert field in card
    assert all({"id", "name", "description", "tags"} <= set(s) for s in card["skills"])
