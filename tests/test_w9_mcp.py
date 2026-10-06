"""Week 9 tests. Needs the MCP SDK (`mcp<2`); skipped where it isn't installed
(the pre-Week-9 suite runs fine on the base interpreter)."""

import os
import re
import sys

import pytest

pytest.importorskip("mcp")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "src"))

import mcp_llm_sim  # noqa: E402
import mcp_wire_capture  # noqa: E402
from mcp_agent import run_questions_sync  # noqa: E402
from mcp_gateway import check_scope  # noqa: E402

SINGLE = os.path.join(BASE, "mcp_config.single.json")
MULTI = os.path.join(BASE, "mcp_config.json")
GATEWAY = os.path.join(BASE, "mcp_config.gateway.json")
REGISTRY_TOOLS = {"list_package_versions", "get_package_version", "get_deprecation_notice"}
DOCS_TOOLS = {"search_docs", "get_openapi_spec"}


def test_agent_module_contains_no_tool_names():
    for rel in ("src/mcp_agent.py", "src/mcp_llm_sim.py"):
        with open(os.path.join(BASE, rel), encoding="utf-8") as fh:
            src = fh.read()
        for name in REGISTRY_TOOLS | DOCS_TOOLS:
            assert name not in src, f"{rel} hard-codes tool name {name}"


def test_discovery_goes_from_two_to_five_via_config_only():
    single = run_questions_sync(SINGLE, [])
    multi = run_questions_sync(MULTI, [])
    assert single["tool_count"] == 2 and set(single["discovery"]) == {"docs-search"}
    assert multi["tool_count"] == 5
    assert set(multi["discovery"]["package-registry"]) == REGISTRY_TOOLS
    assert set(multi["discovery"]["docs-search"]) == DOCS_TOOLS


def test_registry_tool_is_called_and_shows_in_trace():
    out = run_questions_sync(MULTI, ["Is acme-sdk 2.9.1 deprecated?"])
    step = out["traces"][0]["steps"][0]
    assert (step["server"], step["tool"]) == ("package-registry", "get_deprecation_notice")
    assert "DEPRECATED" in out["traces"][0]["answer"]


def test_version_matrix_is_attached_as_resource_not_a_tool():
    out = run_questions_sync(SINGLE, [])
    assert "Client.sendMessage" in out["resource_text"]
    assert not any("matrix" in t["name"] for t in out["tools"])


def test_legacy_error_is_opaque_and_prompt_error_recovers():
    q = ["Search the docs for a Client.send example on sdk v4."]
    before = run_questions_sync(SINGLE, q, extra_env={"DOCS_SERVER_STYLE": "legacy"})["traces"][0]
    after = run_questions_sync(SINGLE, q, extra_env={"DOCS_SERVER_STYLE": "prompt"})["traces"][0]
    assert before["steps"][0]["is_error"] and before["steps"][0]["result_text"].endswith("Error 3")
    assert len(before["steps"]) == 1 and "sendMessage" in before["answer"]
    assert after["steps"][0]["is_error"] and "latest published is v3" in after["steps"][0]["result_text"]
    assert not after["steps"][-1]["is_error"] and after["steps"][-1]["arguments"]["sdk_version"] == "v3"
    assert "sendMessage" not in after["answer"]


def test_wire_capture_is_fully_hand_annotated_and_ordered():
    wire = mcp_wire_capture.capture()
    assert mcp_wire_capture.missing_annotations(wire) == []
    methods = [m["raw"].get("method") for m in wire["messages"]]
    assert methods == ["initialize", None, "notifications/initialized", "tools/list", None, "tools/call", None]
    assert "model call happens in the HOST" in wire["where_the_model_call_happens"]


def test_gateway_denial_is_recoverable_and_audited(tmp_path):
    out = run_questions_sync(GATEWAY, ["Is acme-sdk 2.9.1 deprecated?"])
    steps = out["traces"][0]["steps"]
    assert steps[0]["tool"] == "get_deprecation_notice" and steps[0]["is_error"]
    assert steps[0]["result_text"].startswith("SCOPE_DENIED") and "alternative_tool: get_package_version" in steps[0]["result_text"]
    assert steps[1]["tool"] == "get_package_version" and not steps[1]["is_error"]


def test_check_scope_unit():
    entry = {"caller": "c", "denied_tools": ["x"], "alternatives": {"x": "y"}}
    assert check_scope(entry, "y", ["x", "y"]) is None
    assert check_scope(entry, "x", ["x", "y"]).startswith("SCOPE_DENIED")
    assert check_scope(None, "y", ["y"]).startswith("AUTH_REQUIRED")


def test_slot_extraction_and_tool_selection_unit():
    slots = mcp_llm_sim.extract_slots("When was acme-sdk 3.1.0 released?")
    assert slots["package"] == "acme-sdk" and slots["version"] == "3.1.0"
    assert mcp_llm_sim.select_tool("hello there", [{"name": "a_tool", "description": "x", "inputSchema": {}}]) == (None, None)


def test_risk_note_is_exactly_five_lines_and_deliverables_exist():
    out = os.path.join(BASE, "output", "w9")
    with open(os.path.join(out, "risk_note.md"), encoding="utf-8") as fh:
        lines = [ln for ln in fh.read().splitlines() if ln.strip()]
    assert len(lines) == 5 and [int(re.match(r"(\d)\.", ln).group(1)) for ln in lines] == [1, 2, 3, 4, 5]
    assert "DON'T SHIP" in lines[4]
    with open(os.path.join(out, "agent_diff.txt"), encoding="utf-8") as fh:
        assert "agent module lines changed: 0" in fh.read()
