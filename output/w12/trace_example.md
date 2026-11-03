# One end-to-end trace — one trace id across the agent hop and the MCP hop

Question: *How do I send a message?* — IDE sent `sdk_version=2.4`.

## `fixed`: trace id `t_1448105384` on every span, both sides of the hop

| # | Span | Side | Stage | Trace id | Parent | Latency | Kind | Tokens in/out | Cost |
|---:|---|---|---|---|---|---:|---|---:|---:|
| 1 | request | engine | request | `t_1448105384` | `` | 0.0 ms | measured | 0/0 | $0.00000 |
| 2 | redact_input | engine | redact | `t_1448105384` | `s1` | 0.0 ms | measured | 0/0 | $0.00000 |
| 3 | resolve_version | engine | resolve | `t_1448105384` | `s1` | 0.8 ms | measured | 0/0 | $0.00000 |
| 4 | agent_loop | engine | agent | `t_1448105384` | `s1` | 83.1 ms | measured | 0/0 | $0.00000 |
| 5 | plan:lap1 | engine | plan | `t_1448105384` | `s4` | 816.6 ms | modelled | 112/49 | $0.00029 |
| 6 | tool:search_docs | engine | tool | `t_1448105384` | `s5` | 70.3 ms | measured | 0/0 | $0.00000 |
| 7 | mcp:search_docs | server | tool | `t_1448105384` | `s6` | 61.0 ms | measured | 0/0 | $0.00002 |
| 8 | tool:search_docs | engine | tool | `t_1448105384` | `s5` | 71.3 ms | measured | 0/0 | $0.00000 |
| 9 | mcp:search_docs | server | tool | `t_1448105384` | `s7` | 2.2 ms | measured | 0/0 | $0.00002 |
| 10 | plan:lap2 | engine | plan | `t_1448105384` | `s4` | 432.9 ms | modelled | 632/6 | $0.00053 |
| 11 | tool:verify_sample | engine | gate | `t_1448105384` | `s8` | 1.1 ms | measured | 0/0 | $0.00000 |
| 12 | plan:lap3 | engine | plan | `t_1448105384` | `s4` | 871.8 ms | modelled | 662/48 | $0.00072 |
| 13 | tool:lookup_deprecation | engine | tool | `t_1448105384` | `s10` | 6.7 ms | measured | 0/0 | $0.00000 |
| 14 | mcp:lookup_deprecation | server | tool | `t_1448105384` | `s11` | 0.2 ms | measured | 0/0 | $0.00002 |
| 15 | tool:lookup_deprecation | engine | tool | `t_1448105384` | `s10` | 8.1 ms | measured | 0/0 | $0.00000 |
| 16 | mcp:lookup_deprecation | server | tool | `t_1448105384` | `s12` | 0.0 ms | measured | 0/0 | $0.00002 |
| 17 | tool:lookup_deprecation | engine | tool | `t_1448105384` | `s10` | 9.0 ms | measured | 0/0 | $0.00000 |
| 18 | mcp:lookup_deprecation | server | tool | `t_1448105384` | `s13` | 0.1 ms | measured | 0/0 | $0.00002 |
| 19 | plan:lap4 | engine | plan | `t_1448105384` | `s4` | 608.5 ms | modelled | 1077/3 | $0.00087 |
| 20 | compose | engine | generate | `t_1448105384` | `s1` | 3211.3 ms | modelled | 580/281 | $0.00159 |

Total: 6023 ms critical path, $0.00410. Server spans: 5, every one carrying `t_1448105384` and pointing at the client span that made the call.

## `naive`: the same request, trace id `t_c4934cb741` — the trace breaks at the hop

5 server spans came back, with trace ids: `(empty)`. The server logged its work under a trace id nobody can join to the request.

Raw JSON of both: `trace_example.json`. The engine's request log (`runs/fixed/requests.jsonl`) and the MCP server's own span log (`runs/fixed/mcp_server_spans.jsonl`) are redacted on write; the planted canary secrets appear in neither (assertion `pii_canaries_absent`).
