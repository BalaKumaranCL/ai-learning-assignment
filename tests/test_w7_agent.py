"""Tests for the Week 7 Task Set E build: tool descriptions, budget
enforcement, workflow shape, and race scoring."""

import json
import os

import pytest

from agent_tools import TOOLS, TOOLS_BY_NAME, call_tool
from agent_loop import run_agent
from fixed_workflow import run_workflow
from scoring import score_answer

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _load_questions():
    with open(os.path.join(DATA_DIR, "w7_questions.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Third tool: one job, typed/enum parameters, no description overlap.
# ---------------------------------------------------------------------------

def test_exactly_three_tools_named_correctly():
    names = {t["name"] for t in TOOLS}
    assert names == {"search_docs", "get_openapi_spec", "check_deprecation"}


def test_check_deprecation_api_version_is_enum():
    params = TOOLS_BY_NAME["check_deprecation"]["parameters"]
    assert params["api_version"]["type"] == "string"
    assert params["api_version"]["enum"] == ["v2", "v3"]
    assert params["api_version"]["required"] is True


def test_check_deprecation_description_names_one_job_and_excludes_the_others():
    desc = TOOLS_BY_NAME["check_deprecation"]["description"].lower()
    assert "deprecat" in desc
    # Must not read like a parameter-schema tool or a docs-search tool.
    assert "parameter schema" not in desc.replace("a ", "")  # sanity: no accidental schema claim
    assert "get_openapi_spec" in desc
    assert "search_docs" in desc


def test_no_two_tool_descriptions_claim_the_same_job():
    exclusive_phrases = {
        "search_docs": "prose documentation",
        "get_openapi_spec": "parameter schema",
        "check_deprecation": "deprecated",
    }
    for owner, phrase in exclusive_phrases.items():
        for other in TOOLS:
            desc = other["description"].lower()
            if other["name"] == owner:
                assert phrase in desc
            else:
                # the other tools may mention the phrase only to say "don't use me for this"
                if phrase in desc:
                    assert "do not use this" in desc


# ---------------------------------------------------------------------------
# Budgets: all four are actually checked, and a run that hits one terminates
# cleanly (no exception, no answer, a typed reason).
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("budget_key", ["max_iterations", "max_tokens", "max_cost_usd", "max_wall_clock_s"])
def test_each_budget_can_independently_terminate_the_loop(budget_key):
    question = _load_questions()["budget_demo_question"]
    unlimited = 10**9
    budgets = {
        "max_iterations": unlimited,
        "max_tokens": unlimited,
        "max_cost_usd": unlimited,
        "max_wall_clock_s": unlimited,
    }
    tight = {"max_iterations": 2, "max_tokens": 400, "max_cost_usd": 0.0005, "max_wall_clock_s": 0.001}
    budgets[budget_key] = tight[budget_key]

    result = run_agent(question, budgets=budgets, sleep_per_lap_s=0.01)

    assert result["terminated_by_budget"] == budget_key
    assert result["answer"] is None
    assert result["log"][-1]["event"] == "budget_terminated"


def test_agent_on_a_normal_question_does_not_hit_any_budget():
    questions = _load_questions()["questions"]
    result = run_agent(questions[0])
    assert result["terminated_by_budget"] is None
    assert result["answer"] is not None


# ---------------------------------------------------------------------------
# Fixed workflow: same tools, same output contract, no loop, no branching
# on the STEP sequence (always exactly 3 calls, in the same order).
# ---------------------------------------------------------------------------

def test_workflow_always_calls_exactly_three_tools_in_fixed_order():
    for q in _load_questions()["questions"]:
        result = run_workflow(q)
        names = [c["name"] for c in result["tool_calls"]]
        assert names == ["check_deprecation", "get_openapi_spec", "search_docs"]


def test_agent_and_workflow_share_the_same_output_contract():
    q = _load_questions()["questions"][0]
    agent_result = run_agent(q)
    workflow_result = run_workflow(q)
    assert set(agent_result.keys()) == set(workflow_result.keys())


def test_workflow_passes_every_race_question():
    for q in _load_questions()["questions"]:
        result = run_workflow(q)
        assert score_answer(q, result), f"{q['id']} failed: {result['answer']}"


def test_agent_passes_every_race_question():
    for q in _load_questions()["questions"]:
        result = run_agent(q)
        assert score_answer(q, result), f"{q['id']} failed: {result['answer']}"


# ---------------------------------------------------------------------------
# check_deprecation itself: resolves deprecated names to a valid lookup_key,
# and leaves non-deprecated / unknown names alone.
# ---------------------------------------------------------------------------

def test_deprecated_name_resolves_to_a_real_openapi_spec_key():
    result = call_tool("check_deprecation", {"name": "Client.sendMessage", "api_version": "v3"})
    assert result["deprecated"] is True
    spec = call_tool("get_openapi_spec", {"endpoint": result["lookup_key"], "api_version": "v3"})
    assert spec["found"] is True


def test_unknown_name_is_not_deprecated():
    result = call_tool("check_deprecation", {"name": "Client.close", "api_version": "v3"})
    assert result["deprecated"] is False
    assert result["replacement"] is None
