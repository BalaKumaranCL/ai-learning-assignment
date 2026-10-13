# Verdict: KILL the docs squad, keep the single agent (for this task)
Sunk-cost bias, out loud: I built the orchestrator and two workers last week and part of me wants to keep them because that work is "already spent" — that is not evidence, so I'm ignoring it.
Pass rate: tied 10/10 vs 10/10 on the same 10 cases, so the squad bought no quality (and quality parity is partly by construction: both arms share one answer composer).
Tokens: 16,552 vs 7,673 = 2.2x the re-send bill; cost per question $0.002795 vs $0.001241, and the biggest slice (37.5%) is the orchestrator -> code-sample worker hop.
Speed: modelled p50 7.6 s vs 3.4 s — every question pays 6-8 model calls instead of 2-4.
Reliability: the injected 500 on Q6 made the orchestrator silently ship an unverified answer (a lie by omission) and fail that case; the single agent has no worker to lose.
Multi-agent would earn its keep only with independent subtasks that can run in parallel or need genuinely different instructions; here the code worker waits on the version worker's result, so there is no parallelism to win.
Re-run if that changes (a real model, or a task with parallel branches); I ran the multi arm once and did not re-run it hoping for a win.
Caveat: simulated model and modelled latency, so this settles the COST of the pattern, not whether a real model's narrow prompts would answer better.
