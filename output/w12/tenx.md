# The 10x plan — what breaks first when this ships in-IDE to all 9,000 integrators

**Every limit and every traffic figure below is an ASSUMPTION** (this repo has no provider contract and no usage data); the per-question tokens, calls and server time are measured. Change a constant in `src/w12_costs.py` and the table moves.

1x = a pilot to 900 integrators; 10x = all 9,000. Assumed: 35% are active on a given day, 8 questions each, 15% of the day's questions land in the peak hour -> 2,520 questions/day at 1x, 25,200 at 10x, peak 6.3 questions/min at 1x.

## What breaks, in order

| Order | Constraint | Load at 1x | Assumed limit | **Breaks at** | Basis (measured) |
|---:|---|---:|---:|---:|---|
| 1 | Monthly budget | 300.5 | 2,000 | **6.7x** | $0.00397 per question |
| 2 | LLM input tokens per minute | 1.898e+04 | 250,000 | **13.2x** | 3,013 input tokens per question (transcript resent every lap) |
| 3 | LLM requests per minute | 31.99 | 1,000 | **31.3x** | 5.1 model calls per question (laps + compose) |
| 4 | MCP server throughput (1 process, serial) | 0.0006182 | 1.0 | **1617.5x** | 4.9 calls per question x 1.2 ms measured server time per call |

**First scaling limit to break: Monthly budget at 6.7x.** Monthly spend at 1x is $300; at 10x about $3,005 against the assumed $2,000 budget.

**And a limit that is already broken at 1x:** measured end-to-end p99 is 8,059 ms against an in-IDE target of 3,000 ms (BREACHED before any growth). The cause is structural, not load: 4.1 sequential model calls per question (each ~0.6 s modelled) plus the composer. More traffic does not make it slower here, but nobody types a question into an IDE and waits 5-8 seconds.

## What I would do, ranked and costed (from the stage table)

| # | Change | Saves (measured basis) | Cost to do |
|---|---|---|---|
| 1 | Return lifecycle (deprecated / removed / replaced-by) **inside** the search result, server-side, instead of a separate sweep lap | removes ~1 of 4.1 laps: ~$0.00060/question (15% of cost) and ~0.6 s | one afternoon: the data is already in `symbols.json`; `search_docs` would join it |
| 2 | Run the planner on a smaller model than the composer (assumed 5x cheaper) | planner is 61% of cost: ~$0.00195/question (49%) | needs a real eval of planner quality: the trajectory suite exists for exactly this |
| 3 | Cache the version-scoped search (same question + version -> same chunks) | tool stage is ~2% of cost, so little money, but it removes the MCP hop from the hot path | cheap; invalidate on every docs release |
| 4 | Skip the agent for questions the resolver + one search can answer (factual, how-to with no named symbol) | 2-3 of 4.1 laps on those | needs a router; measure its misroutes with the trajectory eval first |

None of these is done. Only #1 would move the first limit that breaks (monthly budget): it moves 6.7x to roughly 7.9x.
