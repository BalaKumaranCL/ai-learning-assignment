# Week 9 Practical — Task Set E: bolt on the package-registry server without touching the agent

**MCP in one paragraph.** MCP is a standard "socket" between an AI app (the
*host*) and tools (*servers*). The host asks each server "what tools do you
have?" at runtime (`tools/list`), so adding a tool server is a config edit,
not a code change. The AI model runs in the host — a server only offers
tools.

Run: `python -m venv .venv-mcp && .venv-mcp\Scripts\pip install -r requirements.txt && .venv-mcp\Scripts\python run_w9.py`
(needs `mcp<2`; FastMCP was renamed in v2). Tests: `.venv-mcp\Scripts\python -m pytest` (115 pass; on the
base interpreter the Week 9 file skips cleanly).

## What had to be built first

Like Week 7, the "app you already built in Week 9" didn't exist in git. Built
from scratch: our own `docs-search` server (`mcp_servers/docs_search_server.py`),
the MCP host/agent (`src/mcp_agent.py`), and a **stand-in** for DevRel's
package-registry server (`third_party/package_registry/`) — the real one was
not supplied, so its facts below are about the stand-in. The model is the
deterministic stand-in `src/mcp_llm_sim.py` (repo convention: no live LLM
call anywhere); it contains no tool names.

## Results (all produced by `run_w9.py` into `output/w9/`)

| Requirement | Result | File |
|---|---|---|
| 1. Config-only second server, provable call | `get_deprecation_notice` called on `package-registry` for "Is acme-sdk 2.9.1 deprecated?" | `trace_multi_server.json` |
| 2. Zero changed lines in agent module | **0** (sha256 identical, `git diff --no-index` empty) | `agent_diff.txt`, `config_diff.txt` |
| 3. Tool count from `tools/list` | **2 → 5**: `search_docs`, `get_openapi_spec` → + `list_package_versions`, `get_package_version`, `get_deprecation_notice` | `discovery.json` |
| 4. Raw wire, hand-annotated | initialize → initialized → tools/list → tools/call, every top-level field annotated (test fails if one is missing) | `wire.json` |
| 5. Docstring-as-prompt + recoverable error | opaque `Error 3` → `UNSUPPORTED_VERSION … latest published is v3 … retry_with: sdk_version=v3`; 1 failed call → fail + successful retry | `error_before_after.md` |
| 6. 5-line risk note | verdict: **don't ship as-is**; ship only behind the gateway | `risk_note.md` |
| Bonus: gateway + scoped token | one front door, 5 tools fanned out; denied tool reaches the model as `SCOPE_DENIED … alternative_tool: get_package_version`; 5 audit lines | `gateway_transcript.md`, `gateway_audit.log` |

Wire-level model-call statement (one line, also in `wire.json`): the model
call happens in the host (`mcp_agent.py` → `mcp_llm_sim.decide_next`); the
JSON-RPC exchange is local plumbing and the server contains no model call.

## Honest caveats

- **The before/after "model" is a stand-in.** The AFTER path (read `retry_with:`, retry) is real code reacting to the
  real server text. The BEFORE path (opaque error → stale v2 sample) is *modelled* on the failure the brief names; a real
  model would vary. It illustrates what the rewrite prevents; it is not a measurement.
- **The zero-diff proof compares agent files before/after the runs** (`git diff --no-index` on snapshots) because
  Week 9 has no earlier commit to diff against. It also has a guard test: no tool name appears in the agent source.
- **The registry server is a stand-in**, so the risk note audits behavior I wrote (it logs full arguments + token tail,
  see `registry_access.log`) and says plainly that the real server's author and logs are unknown.
- Design choices from the brief's "common mistakes": the version-support matrix is a **resource** the host attaches
  (not a tool); errors say `UNSUPPORTED_VERSION`/`NOT_FOUND` + "the service itself is up" so "doesn't exist" ≠ "down";
  no LLM call inside any server; the tool list is never hard-coded.
- Gateway denied tools stay *listed* (so the denial is demonstrable); in production also hide them from `tools/list`.
  The gateway token travels in the process env because stdio has no headers (a remote server would use a bearer token).
