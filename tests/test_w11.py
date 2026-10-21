import json
import os
from datetime import datetime

import deprecations
import w11_hunt as H
import w11_logs as L
import w11_service as S
from assertions import no_deprecated_symbol_unflagged

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW = (datetime(2026, 10, 12), datetime(2026, 10, 19))
INCIDENT_Q = "give me a code sample for sending a message with the client"


def _run(question, flt, pv):
    return S.run_request({"ts": "2026-10-15T14:37:12", "user_id": "u", "app": "a",
                          "question": question, "sdk_version_filter": flt}, "t_test", prompt_version=pv)


# ---- the shared definition of "deprecated" ---------------------------------

def test_deprecated_patterns_match_real_call_shapes():
    assert deprecations.find_deprecated_symbols("client.sendMessage('x')") == ["Client.sendMessage"]
    assert deprecations.find_deprecated_symbols("Client(AuthConfig(token=T))") == ["AuthConfig.token"]
    assert deprecations.find_deprecated_symbols("client.send(message='x')") == []


def test_v2_request_or_migration_note_excuses_a_deprecated_symbol():
    code = "client.sendMessage('x')"
    assert deprecations.unflagged_deprecated_symbols(code, None) == ["Client.sendMessage"]
    assert deprecations.unflagged_deprecated_symbols(code, "v2") == []
    assert deprecations.unflagged_deprecated_symbols(code + " is deprecated, use Client.send", None) == []
    # a refusal that only echoes the question is not an answer
    assert deprecations.unflagged_deprecated_symbols(code, None, answered=False) == []


def test_new_assertion_fails_on_the_stale_sample():
    passed, _ = no_deprecated_symbol_unflagged(
        {"answer": "client.sendMessage('x')", "sdk_version_filter": None, "answered": True}, {})
    assert passed is False


# ---- the incident, before and after ----------------------------------------

def test_docs_v1_serves_the_archived_v2_sample_to_an_unfiltered_caller():
    t = _run(INCIDENT_Q, None, "docs_v1")
    assert t["cited_chunk_id"] == "client_v2::archive::0"
    assert "sendMessage" in t["answer"]
    assert t["prompt_version"] == "docs_v1"


def test_docs_v2_answers_the_same_request_with_a_current_sample():
    t = _run(INCIDENT_Q, None, "docs_v2")
    assert t["answered"] and "client.send(" in t["answer"]
    assert not deprecations.find_deprecated_symbols(t["answer"])
    assert all(v == "v3" for v in t["retrieved_sdk_versions"])
    assert t["sdk_version_filter"] is None and t["sdk_version_filter_applied"] == "v3"


def test_docs_v2_still_serves_v2_code_when_v2_is_asked_for():
    # the over-fix guard (eval case E33)
    t = _run("In SDK v2, show me a code sample of Client.sendMessage", "v2", "docs_v2")
    assert t["answered"] and "sendMessage" in t["answer"]


def test_docs_v2_does_not_write_samples_from_memory():
    # no fenced sample anywhere in a v3 context -> refuse, don't invent one
    t = _run("show me a code sample for the proxy_settings parameter", "v3", "docs_v2")
    assert "sendMessage" not in t["answer"] and "token=" not in t["answer"]


def test_every_trace_has_the_fields_the_incident_needs():
    t = _run(INCIDENT_Q, None, "docs_v2")
    for key in ("prompt_version", "retrieved_chunk_ids", "spans", "totals"):
        assert key in t
    stages = {s["stage"] for s in t["spans"]}
    assert stages == {"retrieval", "generation", "tools"}
    for s in t["spans"]:
        for key in ("latency_ms", "tokens_in", "tokens_out", "cost_usd"):
            assert key in s
    assert abs(t["totals"]["cost_usd"] - sum(s["cost_usd"] for s in t["spans"])) < 1e-9


def test_v1_makes_no_tool_calls_so_its_tool_stage_costs_nothing():
    t = _run(INCIDENT_Q, None, "docs_v1")
    assert [s["stage"] for s in t["spans"]] == ["retrieval", "generation"]


# ---- the drill logs ---------------------------------------------------------

def test_drill_logs_contain_exactly_one_findable_bad_answer():
    lines = L.read_logs(os.path.join(BASE_DIR, "data", "w11_prod_logs.jsonl"))
    result = H.hunt_v1(lines, WINDOW)
    assert len(result["candidates"]) == 1
    assert result["candidates"][0]["prompt_version"] == "docs_v1"
    # the planted trace carries the context ids that prove retrieval served the v2 page
    assert "client_v2::archive::0" in result["candidates"][0]["retrieved_chunk_ids"]


def test_indexed_hunt_agrees_with_the_scan_hunt_on_the_wired_logs():
    lines = L.read_logs(os.path.join(BASE_DIR, "data", "w11_prod_logs_v2.jsonl"))
    scan = H.hunt_v1(lines, WINDOW)["candidates"]
    indexed = H.hunt_indexed(lines, WINDOW)["candidates"]
    assert [c["trace_id"] for c in scan] == [c["trace_id"] for c in indexed]
    assert len(indexed) == 1


def test_v1_log_schema_has_no_output_index_and_v2_does():
    t = _run(INCIDENT_Q, None, "docs_v1")
    assert "output_flags" not in L.to_log_line(t, "v1")
    assert L.to_log_line(t, "v2")["output_flags"]["deprecated_symbols_unflagged"] == ["Client.sendMessage", "AuthConfig.token"]


def test_question_only_search_is_full_of_wrong_leads():
    lines = L.read_logs(os.path.join(BASE_DIR, "data", "w11_prod_logs.jsonl"))
    assert len(H.input_only_search(lines, WINDOW)) > 10


# ---- the suite --------------------------------------------------------------

def test_eval_set_has_the_two_week_11_cases():
    with open(os.path.join(BASE_DIR, "data", "eval_set.json"), encoding="utf-8") as fh:
        cases = {c["id"]: c for c in json.load(fh)}
    assert cases["E32"]["source"].startswith("w11_incident:")
    assert cases["E33"]["sdk_version_filter"] == "v2"
