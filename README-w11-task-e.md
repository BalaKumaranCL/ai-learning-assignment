# Week 11 Practical — Task Set E: find the code sample that used a deprecated method

**Plain-language version.** Someone said "the assistant gave me code that uses a method we retired, sometime last week." That's all we know. We looked through a week of logs, found the one bad answer, worked out *why* it happened (the assistant fetched an old v2 doc page), turned it into a permanent test that fails today and passes after the fix, and counted what the fix costs and what breaks if traffic grows 10x.

Run: `python run_w11.py` (needs `plant_incident.py` run once first), `python run_w11_suite.py`, `python run_w11_hunt.py`.
Tests: `python -m pytest` (138 pass).

## What had to be built first

Like Weeks 7, 9 and 10, there was no Week 11 app in git. Built from scratch on top of the existing retriever and Week-6 suite:

| File | What it is |
|---|---|
| `src/w11_service.py` | The "production" assistant: same retriever/refuse rule as Weeks 4-6, but every request returns a **trace** with one span per stage (retrieval / generation / tools): latency, tokens, dollars, prompt version, context ids. Holds `docs_v1` and `docs_v2`. |
| `src/deprecations.py` | One shared definition of "uses a deprecated method" (from `data/changelog.json`), used by the new assertion, the fix, the log index and the hunt, so they cannot disagree. |
| `src/w11_logs.py`, `plant_incident.py` | Generates 1,006 requests (2026-10-12..20) by running the real service, then plants one bad answer. Two log schemas. |
| `src/w11_hunt.py`, `run_w11_hunt.py` | The hunt, from the vague complaint only; prints each step's line counts and ms. |
| `run_w11_suite.py`, `add_w11_eval_cases.py` | The Week-6 suite re-run **live** against a chosen prompt version; adds cases E32, E33. |
| `run_w11.py` | Writes `trace.json`, `cost_by_stage.md`, `tenx.md`, `replay_summary.json`. |

## Results (all in `output/w11/`)

| Deliverable | File | Headline |
|---|---|---|
| Drill | `drill.md` | Found `t_b3efb0c1df`. Script clock 00:00 (3 ms). **Human stopwatch time and squadmate sign-off are NOT done** (see caveats). Missing field named: `output_flags.deprecated_symbols_unflagged`. |
| Trace | `trace.json` | Per-span latency/tokens/cost, prompt `docs_v1`, context ids `client_v2::archive::0`, `client_v2::archive::1`, `client::structure::1`. Cause: **retrieval** served the archived v2 page, not model memory. |
| Eval case | `data/eval_set.json` (E32, E33) | E32 = the incident; E33 = "caller asks for v2 must still get v2" (the over-fix guard). |
| RED / GREEN | `suite_red.txt`, `suite_green.txt` | **30/33 -> 33/33.** |
| Cost | `cost_by_stage.md` | Incident request: retrieval $0.0000043 / generation $0.0004144 / tools $0 before; after the fix the same request costs $0.00073 (+74%). Across last week's traffic +22.7%. |
| 10x | `tenx.md` | **Rate limit breaks first:** peak 7 req/min today -> 70 at 10x vs an *assumed* 50/min limit (breaks at 7.1x). |
| Deploy | `deploy.md` | `docs_v1` -> `docs_v2`; two-line canary and rollback. |

### RED -> GREEN in plain terms

- **RED, `docs_v1`: 30/33.** Failures: **E32** (the new case) and **E21, E22** — two Week-5/6 cases that have been failing since they were written (an unfiltered caller served a v2 chunk). They share the root cause.
- **GREEN, `docs_v2`: 33/33.** E32 flipped as intended; E21 and E22 flipped as a **side effect** of the same fix, which I am reporting rather than claiming credit for. **No case went from pass to fail** (including E33, the v2-legacy guard).
- Why a *live* suite: `run_eval.py` scores answers stored in `eval_set.json`, so changing a prompt can never change its score. `run_w11_suite.py` re-answers each case's question through the service under a chosen prompt version, which is the only way RED can turn GREEN. A pass = the 4 deterministic assertions (new one: `no_deprecated_symbol_unflagged`) + `expect_answered` where tagged (so "refuse everything" can't look like a fix) + `must_contain`. `judge_v2` is **not** in this gate: Week 6 documents that it marks every refusal "not helpful".
- RED was run and saved *before* `docs_v2` existed in the code.

## The fix (`docs_v2`)

Prompt + retrieval layer (no model routing): default to v3 for callers who send no version (unless the question asks about v2); search "give me a code sample for X" as "X" and look 5 chunks deep for code samples; never write a sample from memory; run `check_deprecation` on every code sample. The fix **costs +22.7% per query** (replay of 798 requests, `replay_summary.json`) and makes the assistant answer more code questions (answered-rate 44.7% -> 52.5%, 83 of 798 answers changed). Generation is 97% of spend either way.

## Honest caveats

- **No squadmate, no human timer.** I planted both incidents, wrote the hunt and ran it. The "time-to-find" is a script clock (milliseconds). The rubric's mm:ss by a named squadmate is **still open**: `drill.md` has blanks for it and the command for a squadmate to plant their own. The bonus's "beat your own time" is likewise only measured structurally (4 steps/69 lines -> 2 steps/1 line) and by script clock.
- **Simulated model, modelled numbers** (repo convention; `llm_sim.py`). Generation is a deterministic stand-in; latency, retrieval cost and tool cost come from documented constants at the top of `src/w11_service.py`. Dollars are **not** billing data.
- **The 10x verdict rests on assumed limits** (50 req/min, 50K tokens/min, $100/month, 2.5 s p99). The verdict flips if your real limit is ≥ 70 req/min. Traffic is synthetic and seeded; its 10:00 burst is realistic in shape, not a measured peak. Modelled p99 (3.2 s) is already over the assumed 2.5 s target at today's volume because of the modelled slow-provider tail; reported, not hidden.
- **The archived-v2 chunks are simulated** (`build_archive_chunks` in `w11_service.py`, like `legacy_v2.py`). They stand in for the old page a docs crawler would have kept; they are what makes a stale sample retrievable.
- **Background traffic was filtered to be clean.** The drill needs exactly one bad answer, so the generator excludes request shapes that trigger the bug. One real instance was found this way (unfiltered `What does Client.stream() return?` returns the archived v2 streaming sample) and is quarantined, listed in `drill.md`, and fixed by `docs_v2`.
- **Canary is a plan, not code.** The 5%/25%/100% split isn't implemented; thresholds are my proposals.
- `tests/test_judge.py` now ignores cases without a Week-6 hand label (E32, E33) — otherwise adding eval cases would break the historical judge-agreement numbers. `run_eval.py` and `assertions.py` also changed: 4th assertion; the static run now knows the archive chunk ids. Static `run_eval.py` results for the original 31 cases are unchanged.
