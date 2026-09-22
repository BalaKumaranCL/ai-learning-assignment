# Week 7 Practical — Task Set E

Race the docs migration agent against a fixed workflow. This week's app
didn't exist yet in this repo (no prior Week 7 commit), so this build adds
the hand-built agent, the fixed workflow, and the race itself in one pass —
reusing Weeks 3–6's docs corpus (`docs/*.md`, `v3`) and simulated legacy v2
content (`src/legacy_v2.py`) as the migration source material.

No live LLM is called anywhere in this project (no API key, nothing in
`requirements.txt`) — see `src/judge.py` and `src/docs_assistant.py` for the
established pattern of simulating the "AI" piece deterministically instead
of spending real API budget on a from-scratch class exercise.
[src/llm_sim.py](src/llm_sim.py) does that for Week 7: it plans tool calls
and writes answers the way a real tool-calling model would, and its token
counts get summed lap over lap like a real API call's would. Token/cost
numbers below use a documented, Haiku-class assumption
(`PRICE_PER_1K_INPUT_USD` / `PRICE_PER_1K_OUTPUT_USD` in `llm_sim.py`), not
a live billing figure — swap in real usage fields from an API response and
nothing else changes.

## 1. The third tool

Requirement: add a tool whose description names exactly one job, uses an
enum for `api_version`, and doesn't overlap the other two.

**Before** (a first draft of the two pre-existing tools, the way most
people write them before hitting the overlap problem):

```
search_docs:      "Search the documentation for information about the Acme
                    SDK, including parameters and how to use them."
get_openapi_spec:  "Look up API parameters and details for a given SDK
                    endpoint and version."
```

Both claim "parameters." A tool-calling model has no principled way to pick
between them — this is exactly the tool-thrash failure mode Week 7 warns
about, and it would only get worse once a third, related tool is added.

**After** (shipped, in [src/agent_tools.py](src/agent_tools.py)):

```diff
- search_docs:      "Search the documentation for information about the
-                     Acme SDK, including parameters and how to use them."
+ search_docs:       "Search the prose documentation (conceptual guides,
+                      reference pages, and usage examples) for how a
+                      feature, class, or parameter is described and used
+                      in practice. [...] Do not use this to get the
+                      authoritative parameter schema of a named endpoint
+                      -- use get_openapi_spec for that. Do not use this to
+                      check whether a name is deprecated or find its
+                      replacement -- use check_deprecation for that."

- get_openapi_spec:  "Look up API parameters and details for a given SDK
-                      endpoint and version."
+ get_openapi_spec:   "Look up the exact, authoritative parameter schema --
+                      names, types, defaults, and which are required --
+                      for one named endpoint or config object, straight
+                      from the OpenAPI spec for one SDK version. Do not
+                      use this for prose explanations or usage examples --
+                      use search_docs for that. Do not use this to check
+                      deprecation status or find a replacement name -- use
+                      check_deprecation for that."

+ check_deprecation:  "Check whether one exact named endpoint, method, or
+                      parameter is deprecated as of a given SDK version,
+                      and if so, return only the replacement's name and a
+                      one-line reason. Do not use this to fetch a
+                      parameter schema -- use get_openapi_spec for that.
+                      Do not use this to search prose documentation -- use
+                      search_docs for that."
+                      parameters: name (string), api_version (enum: v2, v3)
```

Each description now names one job and explicitly rules out the other two.
`get_openapi_spec.api_version` and `check_deprecation.api_version` are both
`enum: [v2, v3]`, not a free string. Tests:
[tests/test_w7_agent.py](tests/test_w7_agent.py)
`test_check_deprecation_api_version_is_enum`,
`test_no_two_tool_descriptions_claim_the_same_job`.

## 2. Architecture — one set of facts, two ways of gathering them

- [src/agent_tools.py](src/agent_tools.py) — the three tools, backed by
  real data: `docs/*.md` (via the Week 4 RRF retriever), `data/openapi_spec.json`
  (parameter schemas, v2 and v3), `data/changelog.json` (deprecations, v3).
- [src/llm_sim.py](src/llm_sim.py) — the simulated model: `plan_step`
  (agent's per-lap decision), `compose_answer` (the **one** function both
  systems use to turn gathered facts into the final answer — this is what
  makes "same output contract" true rather than asserted), token/cost math.
- [src/agent_loop.py](src/agent_loop.py) — the hand-built loop (~60 lines):
  plan → act → observe → repeat, with all four budgets checked every lap.
- [src/fixed_workflow.py](src/fixed_workflow.py) — the same task, zero
  loop: `check_deprecation` → `get_openapi_spec` → `search_docs`, hard-coded,
  every question, every time, then one `compose_answer` call.
- [data/w7_questions.json](data/w7_questions.json) — the 10 race questions
  (Q6/Q7/Q8/Q9 are the required ≥3 cross-version cases: a v2 name is
  deprecated in v3, so the replacement has to be resolved before the schema
  lookup) plus one adversarial question used only by the budget demo.
- [src/race.py](src/race.py), [src/budget_demo.py](src/budget_demo.py),
  [run_w7.py](run_w7.py) — orchestration and CSV/log output.

## 3. Race results — `output/w7/race.csv`

10 questions, both systems, same tools, same `compose_answer`, same
deterministic keyword-based scoring ([src/scoring.py](src/scoring.py)):

| metric | agent | workflow |
|---|---|---|
| pass rate | 1.00 (10/10) | 1.00 (10/10) |
| p50 latency | 0.0310 s | 0.0310 s |
| total tokens (10 q) | 7,673 | 8,006 |
| cost / question | $0.001241 | $0.001610 |

Per-question breakdown (tool calls, tokens, pass/fail, latency for both
systems) is in `output/w7/race_per_question.csv`. Latency here is dominated
by an injected per-step delay standing in for real API round-trip time
(there's no real network call to time), so treat the token and cost columns
as the meaningful comparison, not the latency tie.

Why the workflow costs more despite doing "the same" task: it always runs
all 3 steps, even on the 6 questions where `check_deprecation` +
`get_openapi_spec` alone already answer the question fully — the agent
notices that and stops early. That's a fixable inefficiency (a one-line
"skip step 3 if already answered" branch is still zero loop, zero
re-planning), not evidence the workflow lacks some capability the agent has.

## 4. Budgets — `output/w7/budget_termination_log.txt`

All four budgets (`max_iterations`, `max_tokens`, `max_cost_usd`,
`max_wall_clock_s`) are checked every lap in
[src/agent_loop.py](src/agent_loop.py) — see the four `if total_... >
budgets[...]` checks, each returning a typed, clean termination
(`answer: None`, `terminated_by_budget: "<name>"`) instead of raising or
spinning. `src/budget_demo.py` proves each one can independently be the
budget that fires, using a deliberately open-ended question with no clear
"I'm done" signal (`simulate_thrash` in `llm_sim.plan_step` — a real agent
failure mode, not a rigged one). Excerpt (`max_iterations`, budget=4):

```
{"lap": 3, "decision": {"type": "tool_call", "tool": "search_docs", ...},
 "in_tokens": 867, "out_tokens": 76, "running_total_tokens": 1672, ...}
{"lap": 4, "decision": {"type": "tool_call", "tool": "search_docs", ...},
 "in_tokens": 1253, "out_tokens": 76, "running_total_tokens": 3001, ...}
{"event": "budget_terminated", "budget": "max_iterations", "iterations": 4}
RESULT: terminated_by_budget='max_iterations' iterations=4 total_tokens=3001
        total_cost_usd=0.003374 wall_clock_s=0.063
```

Note the running total climbing lap over lap (172 → 729 → 1672 → 3001) —
every lap resends the whole transcript, so tokens are summed across laps,
never read off just the last one (the other "common mistake" this task
warns about).

## 5. Verdict

Decision rule: does the path vary by input? Across all 10 questions —
including Q6, Q7, Q8, Q9, where `get_openapi_spec`'s argument depends on
what `check_deprecation` found (a v2 name deprecated in v3) — the answer is
no. A fixed 3-step sequence (`check_deprecation` → `get_openapi_spec` →
`search_docs`), with only argument values flowing between steps, answers
every question correctly: pass rate ties at 1.00/1.00, p50 latency ties at
0.031s. The agent runs about 4% fewer tokens and is about 30% cheaper per
question only because it skips the redundant `search_docs` call on the 6
questions the schema alone already answered — a one-line early-exit in the
workflow closes that gap without adding a loop. None of the 10 questions
forces an agent: a later step depending on an earlier step's value isn't
the same as the steps themselves varying, which is the only thing that
would justify one.

## 6. How to reproduce this

```bash
# from the repo root
pip install -r requirements.txt

python run_w7.py                  # race + budget demo, writes output/w7/*
pytest tests/test_w7_agent.py -q  # 15 tests: tools, budgets, workflow shape, scoring
pytest -q                         # full suite, Weeks 3-7
```

## Project layout (additions on top of Weeks 3–6)

```
ai-learning-assignment/
├── data/
│   ├── openapi_spec.json    parameter schemas, v2 + v3 (get_openapi_spec)
│   ├── changelog.json       deprecations, v3 (check_deprecation)
│   └── w7_questions.json    10 race questions + 1 budget-demo question
├── src/
│   ├── agent_tools.py         the three tools
│   ├── llm_sim.py              simulated model: planner + answer composer + token/cost
│   ├── agent_loop.py           hand-built loop, all 4 budgets enforced
│   ├── fixed_workflow.py       same task, 3 hard-coded steps, no loop
│   ├── scoring.py               deterministic keyword-based pass/fail
│   ├── race.py                   runs both systems over the 10 questions
│   └── budget_demo.py             proves each budget can independently fire
├── run_w7.py                       entry point: race + budget demo
├── tests/test_w7_agent.py          15 tests
└── output/w7/
    ├── race.csv                    the 8-number table
    ├── race_per_question.csv       per-question detail
    └── budget_termination_log.txt  4 clean terminations, one per budget
```

## Submission checklist

- [x] Agent (`src/agent_loop.py` via `race.py`) and workflow
      (`src/fixed_workflow.py`) both runnable by one command: `python run_w7.py`
- [x] `output/w7/race.csv` — all 8 numbers over the same 10 docs questions
- [x] `output/w7/budget_termination_log.txt` — all four budgets shown firing independently
- [x] Third tool description diff — Section 1 above
- [x] Verdict naming the question class that does/doesn't need an agent — Section 5 above
