# Trajectory eval on the integrated agent (Week 8, redone)

**n = 13 cases**, each a view on an eval case with the correct tool path written down *before* the agent was scored. 69 tool calls scored.

| Metric | Value |
|---|---:|
| tool-choice accuracy (calls whose need is on some accepted path) | **98.6%** |
| argument validity (every call carried the caller's version; every symbol real or the one asked about) | 100.0% |
| path match (observed sequence is an accepted one) | 92.3% |
| path completeness (every emitted symbol with a deprecation/removal on record was looked up) | 92.3% |
| **outcome pass rate** (the answer passed the suite) | **100.0%** |
| **trajectory pass rate** (path match AND completeness AND arguments) | **84.6%** |
| **outcome-vs-trajectory gap** | **0.154** (2 of 13 cases) |

## Right answer, wrong path

- **T10** (C08, trace `t_fba5537cbf`) — How do I paginate through my messages?  
  emitted code uses ['Client.list_messages.page'] (has a deprecation/removal on record) but the agent never looked it up
- **T13** (C30, trace `t_caf85549a5`) — My key is sk_live_9aXk2Qm7LpR4tZ3vB8nC and send() keeps returning 401. How do I authenticate?  
  observed `exists > lifecycle > search > verify > lifecycle`, accepted: `search > verify > lifecycle`

## Every case

| Case | Outcome | Trajectory | Observed path | Calls | Laps |
|---|---|---|---|---:|---:|
| T01 (C01) | pass | pass | `search > verify > lifecycle` | 6 | 4 |
| T02 (C14) | pass | pass | `search > verify > lifecycle` | 6 | 4 |
| T03 (C18) | pass | pass | `exists > lifecycle > search > verify > lifecycle` | 8 | 6 |
| T04 (C23) | pass | pass | `exists > search > lifecycle` | 4 | 4 |
| T05 (C26) | pass | pass | `exists > lifecycle > search > lifecycle` | 4 | 5 |
| T06 (C20) | pass | pass | `exists > lifecycle > search > verify > lifecycle` | 7 | 6 |
| T07 (C06) | pass | pass | `search > verify > lifecycle` | 5 | 4 |
| T08 (C05) | pass | pass | `(no tools: asked for the version)` | 0 | 0 |
| T09 (C11) | pass | pass | `search > verify > lifecycle` | 5 | 4 |
| T10 (C08) | pass | **FAIL** | `search > verify > lifecycle` | 7 | 4 |
| T11 (C04) | pass | pass | `exists > lifecycle > search > verify > lifecycle` | 9 | 6 |
| T12 (C36) | pass | pass | `search` | 2 | 2 |
| T13 (C30) | pass | **FAIL** | `exists > lifecycle > search > verify > lifecycle` | 6 | 6 |

T13 is the benign kind: the question mentions `send()`, so the agent checks that name first (extra calls, harmless). T10 is the real kind: the sample it emitted uses `page=`, which is deprecated in 2.6 and removed in 3.0, and the agent only looked up its neighbour `per_page`. The answer still passed because the notice about `per_page` and `total_pages` happened to cover the same upgrade — a right answer by luck, not by checking.
