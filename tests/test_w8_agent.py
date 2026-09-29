"""Tests for the Week 8 Task Set E build: trajectory scoring, the
outcome-vs-trajectory gap, the failure-mode zoo, the single mitigation and
its regression check, and the prompt-injection bonus."""

import json
import os

from agent_tools import CALLABLES, TOOLS, is_known_name
from failure_zoo import regression_table, run_zoo, top_failure_mode
from guardrails import guard_output, sanitize_docs_result
from prompt_injection_demo import (
    INJECTION_PAYLOAD,
    MALICIOUS_DOCS_RESULT,
    OBFUSCATED_DOCS_RESULT,
    attack_undefended,
    attack_with_both_layers,
    attack_with_sanitizer,
)
from trajectory_eval import load_expectations, load_questions, run_trajectory_eval

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


# ---------------------------------------------------------------------------
# Requirement 1: 10 expected tool sequences, asserted as a set where more
# than one path is legitimate.
# ---------------------------------------------------------------------------

def test_all_10_w7_questions_have_an_expectation():
    ids = {q["id"] for q in load_questions()}
    assert ids == set(load_expectations().keys())


def test_every_expectation_lists_at_least_one_accepted_sequence():
    for case_id, exp in load_expectations().items():
        assert len(exp["accepted_sequences"]) >= 1, case_id
        for seq in exp["accepted_sequences"]:
            assert set(seq) >= set(exp["required_tools"]), f"{case_id}: {seq} missing a required tool"


def test_three_cases_legitimately_accept_more_than_one_path():
    multi_path = [cid for cid, exp in load_expectations().items() if len(exp["accepted_sequences"]) > 1]
    # Q1, Q2, Q3, Q4, Q5, Q7, Q10 -- every case where a defensive
    # check_deprecation / harmless extra get_openapi_spec doesn't change
    # the answer. Q6/Q8/Q9 deliberately do NOT -- see their "why".
    assert set(multi_path) == {"Q1", "Q2", "Q3", "Q4", "Q5", "Q7", "Q10"}


# ---------------------------------------------------------------------------
# Requirement 2: the four trajectory numbers, with cost as p50 AND max.
# ---------------------------------------------------------------------------

def test_trajectory_eval_reports_all_four_numbers_with_cost_variance():
    result = run_trajectory_eval(require_spec_after_deprecation=False)
    summary = result["summary"]
    for key in ("tool_choice_accuracy", "argument_validity_rate", "step_efficiency_mean", "cost_p50_usd", "cost_max_usd"):
        assert key in summary
    # p50 and max must be reported separately -- a bare mean would hide
    # exactly the runaway-loop case this metric exists to catch.
    assert summary["cost_max_usd"] >= summary["cost_p50_usd"]


def test_tool_choice_accuracy_and_argument_validity_are_perfect_on_the_real_10():
    # The planner never invents an argument or reaches for an outright
    # wrong tool on the real race questions -- its bug is WHEN it stops,
    # not WHICH tools it knows how to call. The zoo's synthetic cases (not
    # this eval) are what exercises a genuine miss on these two metrics.
    result = run_trajectory_eval(require_spec_after_deprecation=False)
    assert result["summary"]["tool_choice_accuracy"] == 1.0
    assert result["summary"]["argument_validity_rate"] == 1.0


# ---------------------------------------------------------------------------
# Requirement 3: the outcome-vs-trajectory gap, and the named
# right-answer-wrong-path case.
# ---------------------------------------------------------------------------

def test_outcome_passes_all_10_but_trajectory_only_7_of_10():
    result = run_trajectory_eval(require_spec_after_deprecation=False)
    assert result["summary"]["outcome_pass_rate"] == 1.0
    assert result["summary"]["trajectory_pass_rate"] == 0.7
    assert result["summary"]["outcome_vs_trajectory_gap"] == 0.3


def test_q6_q8_q9_are_the_named_right_answer_wrong_path_cases():
    result = run_trajectory_eval(require_spec_after_deprecation=False)
    ids = {r["id"] for r in result["right_answer_wrong_path"]}
    assert ids == {"Q6", "Q8", "Q9"}
    for r in result["right_answer_wrong_path"]:
        assert r["missing_tools"] == ["get_openapi_spec"]
        assert r["outcome_pass"] is True


# ---------------------------------------------------------------------------
# Requirements 4 & 5: the zoo, the single mitigation, before -> after, and
# the regression table.
# ---------------------------------------------------------------------------

def test_zoo_covers_five_distinct_failure_modes_before_mitigation():
    before = run_zoo(require_spec_after_deprecation=False)
    failing_modes = {mode for mode, n in before["counts"].items() if n > 0 and mode != "clean"}
    assert failing_modes == {"loop", "wrong_tool", "hallucinated_argument", "silent_giveup", "premature_stop"}


def test_premature_stop_is_the_top_failure_mode():
    before = run_zoo(require_spec_after_deprecation=False)
    assert top_failure_mode(before["counts"]) == "premature_stop"
    assert before["counts"]["premature_stop"] == 3


def test_mitigation_fixes_the_top_mode_and_nothing_else_changes():
    before = run_zoo(require_spec_after_deprecation=False)
    after = run_zoo(require_spec_after_deprecation=True)

    assert before["counts"]["premature_stop"] == 3
    assert after["counts"]["premature_stop"] == 0

    table = regression_table(before["counts"], after["counts"])
    worsened = [row for row in table if row["direction"] == "WORSE"]
    assert worsened == [], f"mitigation made a mode worse: {worsened}"

    unaffected = {"loop", "wrong_tool", "hallucinated_argument", "silent_giveup"}
    for row in table:
        if row["mode"] in unaffected:
            assert row["before"] == row["after"] == 1, row


def test_mitigation_has_a_measured_nonzero_price():
    before = run_trajectory_eval(require_spec_after_deprecation=False)
    after = run_trajectory_eval(require_spec_after_deprecation=True)
    before_cost = sum(r["total_cost_usd"] for r in before["rows"])
    after_cost = sum(r["total_cost_usd"] for r in after["rows"])
    assert after_cost > before_cost, "mitigation must cost something measurable, not be free"


def test_mitigation_does_not_regress_any_of_the_10_race_questions():
    # Backward-compat guard: the fix only ADDS a confirming tool call, it
    # must never flip an already-passing question to a fail.
    after = run_trajectory_eval(require_spec_after_deprecation=True)
    assert after["summary"]["outcome_pass_rate"] == 1.0


# ---------------------------------------------------------------------------
# Classifier sanity: each synthetic zoo case is labeled the mode it was
# built to trigger, not just whatever bucket it happens to fall into.
# ---------------------------------------------------------------------------

def test_synthetic_zoo_cases_land_in_their_intended_mode():
    with open(os.path.join(DATA_DIR, "w8_zoo_cases.json"), "r", encoding="utf-8") as fh:
        cases = json.load(fh)["cases"]

    before = run_zoo(require_spec_after_deprecation=False)
    runs_by_id = {r["id"]: r for r in before["runs"]}
    for case in cases:
        assert runs_by_id[case["id"]]["mode"] == case["failure_mode"], case["id"]


# ---------------------------------------------------------------------------
# Bonus: indirect prompt injection, attack and defense.
# ---------------------------------------------------------------------------

def test_attack_succeeds_undefended():
    answer = attack_undefended()
    assert INJECTION_PAYLOAD in answer


def test_sanitizer_removes_the_payload_but_keeps_legitimate_content():
    answer, hit_count = attack_with_sanitizer()
    assert INJECTION_PAYLOAD not in answer
    assert hit_count >= 1
    assert "max_retries caps how many times" in answer  # legit sentence survives


def test_output_guardrail_independently_catches_an_unsanitized_payload():
    guarded, blocked = guard_output(attack_undefended())
    assert blocked is True
    assert INJECTION_PAYLOAD not in guarded


def test_both_layers_together_block_the_documented_attack():
    guarded, hits, blocked = attack_with_both_layers()
    assert INJECTION_PAYLOAD not in guarded


def test_obfuscated_paraphrase_is_the_honest_residual_risk():
    # This is the documented gap, not a bug: a keyword/pattern guardrail
    # cannot catch a paraphrase with none of its trigger phrases.
    sanitized, hit_count = attack_with_sanitizer(OBFUSCATED_DOCS_RESULT)
    assert hit_count == 0
    assert "stops checking who's on the other end" in sanitized


def test_clean_docs_results_are_never_touched_by_the_sanitizer():
    clean = {
        "query": "chunk_size default",
        "sdk_version": "v3",
        "results": [{"source_file": "streaming.md", "anchor": "chunk_size", "text": "chunk_size defaults to 512."}],
    }
    sanitized, hits = sanitize_docs_result(clean)
    assert hits == 0
    assert sanitized == clean


def test_tools_are_read_only_and_side_effect_free():
    # "Scope the docs tool to read-only" (Set E's bonus) -- verify it, don't
    # just assert it: the only three callables this project's tools expose
    # are exactly the three read/lookup functions, nothing that writes,
    # calls out to the network, or execs.
    assert set(CALLABLES.keys()) == {"search_docs", "get_openapi_spec", "check_deprecation"}
    assert {t["name"] for t in TOOLS} == set(CALLABLES.keys())


def test_is_known_name_tells_real_from_fabricated():
    assert is_known_name("Client.send", "v3") is True
    assert is_known_name("Client.sendMessage", "v3") is True  # real changelog name
    assert is_known_name("Client.sendAsync", "v3") is False  # never existed
