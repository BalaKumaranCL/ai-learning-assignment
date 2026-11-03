# Architecture — one page

**Plain-language version.** A developer asks a question in their IDE. Before anything else the engine works out *which SDK version they are on* (2.4? 3.0?) and refuses to guess if it can't. Then a small agent looks things up through an MCP server — "search the docs for this version", "is this method deprecated?", "does this method exist in this version?" — checks that any code it is about to show really runs on that version, writes the answer with versioned links, and logs the whole trip under one trace id with secrets blanked out.

```
 IDE / CLI ── question + sdk_version? ─────────────────────────────────────────────────────────────┐
                                                                                                    ▼
┌──────────────────────────────────────────── run_w12.py  ->  src/w12_engine.py (Engine.ask) ──────────────────────────────────────────┐
│                                                                                                                                      │
│  1 redact_input      w12_redact      secrets -> [REDACTED:kind]   (local, $0)                       ── trace id minted here ──────────┤
│  2 resolve_version   w12_versions    metadata > pinned > stated > code > error text > mention > ASK (local, $0)  ◄── before any search │
│  3 agent_loop        w12_agent       plan ► act ► observe, parallel calls per lap, 4 tools                                            │
│        │                                                                                                                             │
│        │  plan  ───────────────────►  MODEL CALL #1..n   (one per lap, resends the transcript)        $0.0024/q   61% of cost       │
│        │                                                                                                                             │
│        ├─ 3a exists / lifecycle / search ──┐   discovered at runtime (tools/list), matched by capability, args from each tool's schema │
│        │                                   │   trace_id + parent_span_id travel as arguments                                          │
│        │                       ┌───────────▼──────────────── MCP over stdio ─────────────────────────────┐                            │
│        │                       │  mcp_servers/w12_sdk_docs_server.py   (OUR server; a foreign client can call it: reviewer_client.py)  │
│        │                       │   search_docs ── w12_index ScopedIndex ── v2 index │ v3 index │ SO index (never served)           │
│        │                       │   lookup_deprecation ┐                                                                               │
│        │                       │   symbol_exists ─────┴─ w12_symbols  ◄── corpus/symbols.json  (the one source of truth)             │
│        │                       │   writes ITS OWN span log (redacted on write); returns `_server_span` with the same trace id         │
│        │                       └──────────────────────────────────────────────────────────────────────────┘     tool stage ≈ 2.5% of $│
│        │                                                                                                                             │
│        └─ 3b verify_sample (local) ── w12_codecheck: ast.parse ► imports ► symbols exist in THIS version ► run against a stub   ($0) │
│                                                                                                                                      │
│  4 compose           w12_answer      version line first; verified sample; deprecations unasked; "no longer exists in 3.0";            │
│                                      "no such method"; versioned, clickable sources              MODEL CALL (1)  $0.0014/q  36%      │
│  5 write             w12_trace       one JSON line per request, redacted on write (output/w12/runs/<config>/requests.jsonl)           │
└──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘
                                          │
                                          ▼  answer + citations + trace id

 Offline, same engine:  w12_eval (38 cases, assertions first, judge second)  ·  w12_trajectory (13 cases)  ·  w12_sweep (66 requests)
                        w12_loop (ablation, closed loop, 3.1 drill)  ·  w12_costs (cost / 10x)  ·  w12_report -> output/w12/*.md
```

## Where the model calls happen

Exactly two places, both **stand-ins** in this repo (there is no live LLM anywhere in it — see `src/w12_llm.py`): the **planner** (one call per lap, ~4.1 laps per question) and the **composer** (one call). The judge is a third stand-in, used offline only. Everything else — version resolution, retrieval, the MCP hop, redaction, the code check — is real code with real stopwatch timings.

## Where the money goes (modelled dollars, measured tokens, 102 requests)

| Stage | $/question | share |
|---|---:|---:|
| planner (4.1 laps, transcript resent each lap) | $0.00244 | 61% |
| composer | $0.00144 | 36% |
| MCP tool calls (4.9 calls) | $0.00010 | 2.5% |
| redact / resolve / code check | $0 | 0% |
| **total** | **$0.00397** | |

## The version rule, enforced in three places (so one bug is not a wrong snippet)

1. **Engine** — resolves the version first, passes it into every tool call, and verifies each returned passage is in scope.
2. **Server** — refuses a call with no version (`VERSION_REQUIRED`); one RRF index per major version; a range filter by minor; `assert_scoped` raises if anything out of range slips through.
3. **Code gate** — a sample is only emitted if it parses, imports resolve, every method/argument exists in that version, and it runs against a stub of that version.

Remove (2)'s range filter and 19 of 36 cases fail; remove either of the other two and nothing fails *on this suite* — they are insurance (ablation.md).

## Files

`src/w12_*.py` (engine, agent, answer, index, text, symbols, versions, codecheck, redact, trace, llm, mcp) · `mcp_servers/w12_sdk_docs_server.py` · `mcp_config.w12.json` · `corpus/` (v2.x docs, 3.0 additions, migration guide, changelogs, 19 samples, 12 SO answers, `symbols.json`) · `data/w12/` (cases, labels, trajectory, retrieval) · `reviewer_client.py` · `tests/test_w12.py`.
