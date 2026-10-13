# Week 10 Practical — Task Set E: race the docs squad against the single agent

**Plain-language version.** A "multi-agent" team is a manager AI that hands
pieces of a job to specialist AIs. Every hand-off re-sends context, so a team
can cost much more for the same answer. This week we measured it: same
questions, same scorer, single agent vs a manager + two specialists.

Run: `python run_w10.py` (plain Python, no MCP needed) → `output/w10/`.
Tests: `python -m pytest` (114 pass, 1 skip on the base interpreter; 124 pass in `.venv-mcp`).

## What had to be built first

Like Weeks 7 and 9, there was no Week 10 base app in git. Built
`src/multi_agent.py` (orchestrator + **version worker** with 1 tool +
**code-sample worker** with 2 tools — *not* the deprecation tool, so the
"narrow prompt, fewer tools" idea is actually tested), `src/w10_race.py`, and
`run_w10.py`. Single arm = the shipped Week 7 agent, unchanged. Workers get
minimal hand-offs that always carry the target SDK version — never the whole
v2/v3 reference.

**Which 10 cases?** "Week-6 eval cases" is ambiguous in this repo: Week 6's
31 cases (`data/eval_set.json`) are retrieval answers (many are refusals) that a tool-using agent can't run. Weeks 7 and 8
already treat `data/w7_questions.json` as "the 10 questions", so that's the set used, with
the same deterministic judge (`scoring.score_answer`) for both arms. No case was written or changed. If you meant a different 10, only
`w10_race.load_questions()` changes.

## Results (`output/w10/race_table.md`)

| Metric | Single agent | Squad |
|---|---:|---:|
| Pass rate | 10/10 | 10/10 |
| p50 / p99 latency (modelled) | 3.4 s / 4.6 s | 7.6 s / 8.8 s |
| Total tokens | 7,673 | 16,552 |
| Cost per question | $0.001241 | $0.002795 |

- **Re-send multiplier: 2.2x.** Largest hand-off: *orchestrator → code-sample worker (delegation + worker calls)*, **37.5%** of all multi-arm tokens; next is the orchestrator's final synthesis (30.8%), which re-sends both worker reports. Every hop: `handoffs.log`.
- **Injected 500** (version worker, Q6, both attempts): the orchestrator **retried once, then lied by omission** — shipped an answer with no version check and no disclosure, and failed the judge on that case. A transient 500 is recovered by the retry; a `disclose_failures` flag makes the persistent case degrade honestly. See `failure_case.md`.
- **Verdict (`verdict.md`): KILL** — tied quality, 2.2x tokens/cost, 2.2x latency, worse failure behaviour; sunk-cost bias named.
- **Bonus:** `agent_card.json` + `a2a_lifecycle.md`. The failed case should end **`failed`**, not `input-required` (the version was known; no user answer fixes a 500); `input-required` fits e.g. Q10, where no version is stated.

## Honest caveats

- **Simulated model** (repo convention, see `llm_sim.py`): both arms write the answer with the same composer, so the pass-rate tie is partly by construction. The race measures what the architecture *costs*; it can't show a capability win a real model might get from narrow prompts.
- **Latency is modelled** from call counts (`model_calls×1.0s + tool_calls×0.2s + hops×0.05s`, assumed constants), identically for both arms. p99 with 10 samples is just the slowest case.
- The multi arm was run once; tokens/pass are deterministic, so there was nothing to re-roll.
- AgentCard field names follow the A2A spec's AgentCard definition as read from a2a-protocol.org (v1.0 names `supportedInterfaces`, `securityRequirements`; earlier drafts used `url`/`security`). The `securitySchemes` shape is OpenAPI-style and not verified against a specific spec revision; the URL is a placeholder.
