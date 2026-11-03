# Cost and latency per question, by stage

Measured over **102 requests** (the 36 eval questions + the 66-request version sweep), `fixed` configuration. **Tokens, MCP calls, laps and the code check are measured. Model-call dollars and model-call latency are MODELLED** (no live LLM in this repo: `w12_llm.py` constants, Haiku-class prices from `llm_sim.py`). Treat the dollars as a shape, not a bill.

| Stage | What it is | $/question | % of cost | Mean input tokens | Mean spans | Mean latency (sum of spans) |
|---|---|---:|---:|---:|---:|---:|
| plan | modelled model call | $0.00244 | 61.4% | 2,500 | 4.1 | 2,655 ms |
| generate | modelled model call | $0.00144 | 36.2% | 513 | 1.0 | 2,827 ms |
| tool | MCP round trip (measured) + assumed call price | $0.00010 | 2.5% | 0 | 9.9 | 49 ms |
| redact | local (measured) | $0.00000 | 0.0% | 0 | 1.0 | 0 ms |
| resolve | local (measured) | $0.00000 | 0.0% | 0 | 1.0 | 0 ms |
| gate | local code check (measured) | $0.00000 | 0.0% | 0 | 0.9 | 1 ms |

**Total per question: $0.00397** (p50 $0.00389, p95 $0.00593, max $0.00744). 4.1 model calls for planning + 1 to compose; 4.9 MCP calls; 3,013 input tokens and 366 output tokens per question.

**End-to-end latency (critical path: parallel calls in one lap count once): p50 5,536 ms, p95 7,690 ms, p99 8,059 ms** — almost all of it the two modelled model calls.

Where the money goes: the **planner** (one model call per lap, each resending the whole transcript) and the **composer**. Retrieval, the MCP hop, version resolution, redaction and the code check together are about 2.5% of cost and about 1% of latency.
