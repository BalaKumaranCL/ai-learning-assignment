# Week 10 -- race_table.md: single agent vs docs squad

Same 10 cases (Q1, Q2, Q3, Q4, Q5, Q6, Q7, Q8, Q9, Q10) from `data/w7_questions.json` -- the 10 questions Weeks 7-8 already use; no case written or changed for this race. Same judge for both arms: `scoring.score_answer` (deterministic keyword check, no opinion in it).
Single arm = the shipped Week 7 agent (`agent_loop.run_agent`). Multi arm = `multi_agent.run_squad`: orchestrator + version worker (1 tool) + code-sample worker (2 tools), minimal-context hand-offs that always carry the target SDK version.

| Metric | Single agent | Orchestrator squad |
|---|---:|---:|
| Pass rate | 10/10 (100%) | 10/10 (100%) |
| p50 latency (modelled) | 3.4 s | 7.6 s |
| p99 latency (modelled) | 4.6 s | 8.8 s |
| Total tokens (10 cases) | 7,673 | 16,552 |
| Cost per question | $0.001241 | $0.002795 |

**Context re-send multiplier: 2.2x** (multi 16,552 tokens / single 7,673 tokens). Largest single token share: **orchestrator -> code-sample worker (delegation + worker calls), 37.5% of all multi-arm tokens** (6,203 tokens). Full breakdown below; every hop is in `handoffs.log`.

| Hand-off bucket (multi arm) | Tokens | Share |
|---|---:|---:|
| orchestrator -> code-sample worker (delegation + worker calls) | 6,203 | 37.5% |
| orchestrator: synthesis (resend of both worker reports) | 5,097 | 30.8% |
| orchestrator -> version worker (delegation + worker calls) | 2,073 | 12.5% |
| orchestrator: re-plan after version report (resend of question + report) | 2,029 | 12.3% |
| orchestrator: decompose (question in) | 1,150 | 6.9% |

## Per case

| Case | single pass | multi pass | single tokens | multi tokens | single model calls | multi model calls |
|---|:-:|:-:|---:|---:|---:|---:|
| Q1 | Y | Y | 464 | 1,040 | 3 | 7 |
| Q2 | Y | Y | 461 | 1,018 | 3 | 7 |
| Q3 | Y | Y | 1,303 | 2,440 | 4 | 8 |
| Q4 | Y | Y | 473 | 1,062 | 3 | 7 |
| Q5 | Y | Y | 1,665 | 2,989 | 4 | 8 |
| Q6 | Y | Y | 298 | 1,154 | 2 | 6 |
| Q7 | Y | Y | 1,384 | 2,598 | 4 | 8 |
| Q8 | Y | Y | 289 | 1,159 | 2 | 6 |
| Q9 | Y | Y | 305 | 1,196 | 2 | 6 |
| Q10 | Y | Y | 1,031 | 1,896 | 4 | 8 |

## How to read this (honest caveats)

- **Latency is modelled, not measured** (the repo has no live model): `model_calls x 1.0s + tool_calls x 0.2s + hops x 0.05s`, same formula for both arms, constants are assumptions. With 10 samples nearest-rank p99 is simply the slowest case.
- **Pass rate is a tie partly by construction**: both arms write the answer with the same `llm_sim.compose_answer`, and the simulated model has no accuracy that a narrower prompt could improve. So this race measures what the architecture COSTS; it cannot show a capability win a real model might get from narrow prompts. A real-model rerun is the follow-up.
- Tokens/cost use `llm_sim`'s documented price assumptions (Haiku-class), billed identically in both arms.
- Sensitivity: with the Week 8 `require_spec_after_deprecation` mitigation switched on in BOTH arms the multiplier is 2.0x and pass rates are 10/10 vs 10/10 -- the conclusion does not hinge on that flag.
