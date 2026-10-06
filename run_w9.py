"""Entry point: <venv>/python run_w9.py   (needs `mcp<2`, see requirements.txt)

Runs the Week 9 Task Set E exercise end to end and writes output/w9/*:

  agent_diff.txt         git diff of the agent module, single-server run vs single+registry run
  config_diff.txt        the config change that added server two
  discovery.json         N -> M tool counts + names, taken from the live tools/list results
  trace_multi_server.json  the query that provably calls a registry tool
  wire.json              raw initialize / tools/list / tools/call, hand-annotated
  error_before_after.md  same failing call, legacy docstring/error vs prompt docstring/error
  gateway_*              bonus: audit log + scoped-token transcript
  risk_note.md           (hand-written, not generated)
"""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "src"))

from mcp_agent import run_questions_sync  # noqa: E402
import mcp_wire_capture  # noqa: E402

OUT = os.path.join(BASE, "output", "w9")
AGENT_MODULE_FILES = ["src/mcp_agent.py", "src/mcp_llm_sim.py"]
REGISTRY_QUERY = "Is acme-sdk 2.9.1 deprecated?"
DOCS_QUERY = "What does Client.send take in v3?"
ERROR_QUERY = "Search the docs for a Client.send example on sdk v4."


def _write(name, text):
    with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def _snapshot(label):
    root = os.path.join(tempfile.mkdtemp(prefix="w9snap_"), label)
    for rel in AGENT_MODULE_FILES:
        os.makedirs(os.path.dirname(os.path.join(root, rel)), exist_ok=True)
        shutil.copy2(os.path.join(BASE, rel), os.path.join(root, rel))
    return root


def _git_diff(a, b):
    """`git diff --no-index` between two trees/files; returns (diff text, changed line count)."""
    numstat = subprocess.run(["git", "diff", "--no-index", "--numstat", a, b], capture_output=True, text=True, cwd=BASE).stdout
    full = subprocess.run(["git", "diff", "--no-index", a, b], capture_output=True, text=True, cwd=BASE).stdout
    changed = sum(int(x) for line in numstat.splitlines() for x in line.split("	")[:2] if x.isdigit())
    return full, changed


def _sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()[:16]


def _fmt_trace(trace, tool_names):
    lines = []
    for s in trace["steps"]:
        err = "ERROR" if s["is_error"] else "ok"
        lines.append(f"  lap {s['lap']}: tools/call {s['server']}::{s['tool']}({json.dumps(s['arguments'])}) -> {err}")
        lines.append("      " + s["result_text"].replace("\n", "\n      ")[:600])
    lines.append("  FINAL ANSWER:")
    lines.append("      " + trace["answer"].replace("\n", "\n      ")[:700])
    return "\n".join(lines)


def main():
    os.makedirs(OUT, exist_ok=True)
    for stale in ("registry_access.log", "gateway_audit.log", "wire_capture_registry.log"):
        path = os.path.join(OUT, stale)
        if os.path.exists(path):
            os.remove(path)

    # ---- 1. single-server run, then single + registry run, SAME agent files ----
    before_tree = _snapshot("before")
    single = run_questions_sync(os.path.join(BASE, "mcp_config.single.json"), [REGISTRY_QUERY, DOCS_QUERY])
    multi = run_questions_sync(os.path.join(BASE, "mcp_config.json"), [REGISTRY_QUERY, DOCS_QUERY])
    after_tree = _snapshot("after")

    agent_diff, changed = _git_diff(before_tree, after_tree)
    _write(
        "agent_diff.txt",
        "# git diff of the agent module: BEFORE the single-server run vs AFTER the single+package-registry run\n"
        f"# files compared: {', '.join(AGENT_MODULE_FILES)}\n"
        "# command: git diff --no-index <snapshot-before> <snapshot-after>\n"
        + "".join(f"# sha256[:16] {rel}: before={_sha(os.path.join(before_tree, rel))} after={_sha(os.path.join(after_tree, rel))}\n" for rel in AGENT_MODULE_FILES)
        + (agent_diff if agent_diff else "(git diff output: empty)\n")
        + f"\nagent module lines changed: {changed}\n",
    )
    config_diff, _ = _git_diff("mcp_config.single.json", "mcp_config.json")  # relative to BASE (cwd of the git call)
    _write("config_diff.txt", config_diff)

    names = lambda run: {srv: tools for srv, tools in run["discovery"].items()}  # noqa: E731
    discovery = {
        "source": "live tools/list responses captured by src/mcp_agent.py McpHost.connect (not typed notes)",
        "before": {"config": single["config"], "count": single["tool_count"], "by_server": names(single)},
        "after": {"config": multi["config"], "count": multi["tool_count"], "by_server": names(multi)},
        "summary": f"{single['tool_count']} tools before -> {multi['tool_count']} tools after",
    }
    _write("discovery.json", json.dumps(discovery, indent=2) + "\n")
    _write("trace_multi_server.json", json.dumps({"discovery": multi["discovery"], "traces": multi["traces"]}, indent=2) + "\n")

    # ---- 2. raw wire ----
    wire = mcp_wire_capture.capture(log_path=os.path.join(OUT, "wire_capture_registry.log"))
    gaps = mcp_wire_capture.missing_annotations(wire)
    assert not gaps, f"unannotated wire fields: {gaps}"
    _write("wire.json", json.dumps(wire, indent=2) + "\n")

    # ---- 3. before/after docstring + error rewrite (same failing call) ----
    legacy = run_questions_sync(os.path.join(BASE, "mcp_config.single.json"), [ERROR_QUERY], extra_env={"DOCS_SERVER_STYLE": "legacy"})
    prompt = run_questions_sync(os.path.join(BASE, "mcp_config.single.json"), [ERROR_QUERY], extra_env={"DOCS_SERVER_STYLE": "prompt"})
    lt, pt = legacy["traces"][0], prompt["traces"][0]
    desc = lambda run: next(t["description"] for t in run["tools"] if t["name"] == "search_docs")  # noqa: E731
    md = [
        "# Week 9 -- error_before_after.md",
        "",
        f"Same failing call both times: `{ERROR_QUERY}` -> `search_docs(sdk_version=\"v4\")`. There is no v4 doc set; "
        "the only change between runs is the server's docstring + error text (`DOCS_SERVER_STYLE=legacy|prompt`, "
        "`mcp_servers/docs_search_server.py`). Agent code is identical in both runs.",
        "",
        "> The model in this repo is the deterministic stand-in `src/mcp_llm_sim.py` (no live LLM anywhere in this project). "
        "Its AFTER behavior (read a `retry_with:` hint and retry) is real code reacting to the real server text. Its BEFORE "
        "behavior on an opaque `Error N` (fall back on a stale v2-era sample) is MODELLED on the failure the brief names, "
        "not observed from a real model -- read it as an illustration of what the rewrite prevents.",
        "",
        "## BEFORE -- terse docstring, opaque error",
        "",
        f"tools/list description the model saw: `{desc(legacy)}`",
        "",
        "```",
        _fmt_trace(lt, None),
        "```",
        "",
        "## AFTER -- docstring written as a prompt, recoverable diagnostic",
        "",
        "tools/list description the model saw:",
        "",
        "```",
        desc(prompt).strip(),
        "```",
        "",
        "```",
        _fmt_trace(pt, None),
        "```",
        "",
        "## What moved",
        "",
        "| | before | after |",
        "|---|---|---|",
        f"| tool calls | {len(lt['steps'])} (failed) | {len(pt['steps'])} (1 failed, 1 recovered) |",
        f"| model can tell 'v4 does not exist' from 'service down' | no (`Error 3`) | yes (`UNSUPPORTED_VERSION`, 'service itself is up') |",
        f"| answer cites a source | {'no' if 'No source' in lt['answer'] else 'yes'} | {'yes' if not pt['steps'][-1]['is_error'] else 'no'} |",
        f"| answer uses deprecated v2 `sendMessage` | {'yes' if 'sendMessage' in lt['answer'] else 'no'} | {'yes' if 'sendMessage' in pt['answer'] else 'no'} |",
        f"| answer tells the user which version it is really for | no | {'yes' if 'v3' in pt['answer'] else 'no'} |",
        "",
    ]
    _write("error_before_after.md", "\n".join(md))

    # ---- 4. bonus: gateway + scoped token ----
    gw_cfg = os.path.join(BASE, "mcp_config.gateway.json")
    gw_questions = ["When was acme-sdk 3.1.0 released?", REGISTRY_QUERY]
    ro = run_questions_sync(gw_cfg, gw_questions)  # config token = read-only
    full = run_questions_sync(gw_cfg, gw_questions, extra_env={"MCP_GATEWAY_TOKEN": "tok-docs-assistant-full"})
    gw = ["# Week 9 bonus -- gateway + token scoping", "",
          f"Agent connects to ONE server (`gateway`); it discovered {ro['tool_count']} tools through it: "
          + ", ".join(t["name"] for t in ro["tools"]) + ".", ""]
    for label, run in (("read-only token (get_deprecation_notice denied)", ro), ("full token", full)):
        gw += [f"## {label}", ""]
        for tr in run["traces"]:
            gw += [f"Q: {tr['question']}", "```", _fmt_trace(tr, None), "```", ""]
    with open(os.path.join(OUT, "gateway_audit.log"), "r", encoding="utf-8") as fh:
        audit = fh.read()
    gw += ["## gateway_audit.log (one line per tools/call: caller, tool, package@version)", "", "```", audit.strip(), "```", ""]
    _write("gateway_transcript.md", "\n".join(gw))

    print(f"agent module lines changed between runs: {changed}")
    print(f"discovery: {discovery['summary']}")
    for srv, tools in discovery["after"]["by_server"].items():
        print(f"  {srv}: {', '.join(tools)}")
    print("registry tool called in trace:", [s["tool"] for s in multi["traces"][0]["steps"]])
    print("error recovery:", len(lt["steps"]), "call(s) before ->", len(pt["steps"]), "after")
    denied = [s for s in ro["traces"][1]["steps"] if s["is_error"]]
    print("gateway: denial reached model:", bool(denied), "| audit lines:", len(audit.strip().splitlines()))


if __name__ == "__main__":
    main()
