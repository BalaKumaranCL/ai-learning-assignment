# Week 12 Capstone — Variant E: SDK Docs Answer Engine

**Written for:** a stranger who has just cloned this repo (and for the Friday reviewers). You should not need to ask me anything.

**Plain-language version.** An SDK has two live versions, 2.x and 3.0, and they differ in ways that matter: a method renamed, an argument removed. A developer who copies a 3.0 snippet into a 2.4 project gets code that imports cleanly and then fails in production. This system answers an SDK question **for the developer's actual version**: it works out the version first (and asks if it can't tell), searches only that version's docs, checks that any code it shows really runs on that version, warns about deprecations nobody asked about, says "that method no longer exists in 3.0 — here is the migration" instead of inventing something, and logs the whole trip under one trace id with pasted secrets blanked out.

It is the integration of Weeks 3–11: RAG (3–4), error taxonomy (5), eval suite + judge (6), the agent loop (7), trajectory evals (8), MCP (9), the squad question (10, not needed here), logging and the incident loop (11).

## Run it (one command)

```
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt          # Windows; on macOS/Linux: .venv/bin/pip
.venv\Scripts\python run_w12.py                        # everything, about 2 minutes
```
Python 3.10–3.12 (built and tested on 3.11). If a package is missing, `run_w12.py` prints a one-line fix instead of a traceback.
**On Windows keep the repo in a short path** (for example `C:\work\ai-learning-assignment`): `mcp` installs `pywin32`, whose files sit in deep folders, and `pip` fails with `WinError 206` if the full path passes 260 characters (found by my own clean-folder test — `output/w12/fresh_eyes.md`).

Ask one question:
```
.venv\Scripts\python run_w12.py ask "How do I paginate through my messages?" --version 2.4
.venv\Scripts\python run_w12.py ask "Does client.pollStream still work in 3.0?" --version 2.4
.venv\Scripts\python run_w12.py ask "How do I send a message?" --version 2.4 --naive     # the first wiring: a 2.4 caller gets the 3.0 client
```
Other commands: `demo` (Part 1 of the demo), `eval` (suite + judge + trajectory), `loop` (the closed failure→test loop), `drill31`, `reviewer` (the standalone MCP client). Exit status is 0 only if there is no unexpected failure **and** the judge agrees with the hand labels on ≥ 85%.

### What you should see (the run of 2026-11-02)

```
Suite (fixed)                   : 36 pass, 0 fail, 2 documented-limit XFAIL, of 38 cases
Suite (naive: all seams unfixed): 2 pass, 34 fail, 2 XFAIL
Wrong-version code samples      : 12/29 (41.4%) -> 0/27 (0.0%)
Judge vs hand labels            : 32/36 = 88.9%  (bar 85%)
Trajectory                      : outcome 100% vs trajectory 85%  gap 0.154
Closed loop                     : RED 1 fail -> GREEN 0 fail, regressions: none
RESULT: GREEN
```
Model-call dollars and latency are **modelled** (there is no live LLM in this repo — see "Honest caveats"); counts, tokens and the code checks are real.

## Where everything is (the brief's checklist)

| The brief asks for | Where |
|---|---|
| One command, one entry point, a README a stranger used | `run_w12.py` (this file); fresh-eyes status: `output/w12/fresh_eyes.md` — **not yet done by a person** |
| Tuesday's seam list, unedited, each marked | `output/w12/seams.md` — 26 seams, each *fixed / accepted / ran-out-of-time* |
| One-page architecture sketch | `output/w12/architecture.md` |
| Full eval-suite output, pass rate per mode, n, judge agreement | `output/w12/EVAL_REPORT.md` (+ `suite_fixed.json`, `suite_naive.json`) |
| Re-scored taxonomy, 4–7 modes, frequency, severity, a trace id each, ≥1 NEW | `output/w12/taxonomy.md` — 7 modes, 3 NEW |
| Trajectory eval + the outcome-vs-trajectory gap | `output/w12/trajectory.md` — n=13, gap 0.154 |
| One end-to-end trace, cost/latency per span, trace id intact across both hops | `output/w12/trace_example.md` / `.json` and `output/w12/runs/fixed/requests.jsonl` + `mcp_server_spans.jsonl` |
| Top 3 weaknesses, written before anyone asked | `output/w12/weaknesses.md` (dated 2026-11-02; written before the first suite run) |
| Cost per question + the 10× plan naming what breaks first | `output/w12/cost_by_stage.md`, `output/w12/tenx.md` |
| Fresh-eyes note | `output/w12/fresh_eyes.md` (template + status — **open**) |
| The 10-minute demo script | `output/w12/demo_script.md` |
| Bonus: execute the check | `output/w12/bonus_execute_check.md` |

### The eight requirements

1. **RAG with versioned, clickable citations** — `src/w12_index.py` (Week 3–4 loader + structure-aware chunker + TF-IDF/BM25/RRF, now with version metadata the code enforces). Every citation names its version ("Acme SDK 2.x", "Acme SDK 3.0"); assertion `citations_versioned`.
2. **Agent loop, ≥ 3 tools, MCP tools discovered at runtime** — `src/w12_agent.py`: search · lifecycle lookup · symbol-exists (all three over MCP) + a local `verify_sample`. The agent file contains no MCP tool name (a test greps for it).
3. **One MCP server of my own, called by a client that isn't mine** — `mcp_servers/w12_sdk_docs_server.py`; `reviewer_client.py` imports nothing from this repo (transcript: `output/w12/foreign_client_transcript.md`). *A reviewer from another squad has not yet run it: open.*
4. **Eval suite on the integrated system, one command, assertions before judges, judge ≥ 85%** — `src/w12_eval.py`, `src/w12_assertions.py`, `src/w12_judge.py`, `data/w12/`.
5. **Taxonomy re-scored, one mode NEW** — `src/w12_eval.py::taxonomy`; three NEW modes (version dropped at the hop, trace lost at the hop, secret in the server's log).
6. **Trajectory eval ≥ 10 cases** — `src/w12_trajectory.py`, `data/w12/trajectory_cases.json`.
7. **Logging across both hops, PII held** — `src/w12_trace.py`, `src/w12_redact.py`; assertions `trace_unbroken` and `pii_canaries_absent`.
8. **A closed loop live + cost + 10×** — `python run_w12.py loop`; `tenx.md`.

## What is in the repo that is NOT real

Read this before you trust a number.

- **No live LLM.** The agent's planner, the answer composer and the judge are deterministic stand-ins (repo convention since Week 7: `src/llm_sim.py`, `src/w12_llm.py`). Tokens are estimated from text length; dollars and model-call latency use documented assumed constants (Haiku-class prices). The brief's "cost per question" is therefore a shape, not a bill.
- **The "SDK" is a stand-in.** `corpus/symbols.json` is a table I wrote of what exists in which version. "The code runs" means it runs against a stub generated from that table. If the table is wrong, everything agrees and is wrong.
- **The corpus is small and synthetic:** v2.x reference pages, 3.0 additions, a migration guide, two changelogs, **19** samples (the brief says 200), **12** Stack Overflow answers (the brief says 50), no open-issues export. The 3.0 pages are Week 3's own six pages, untouched.
- **The hand labels were written by the assistant that built the system**, not by a human, and the judge was tuned earlier on answers I could see were fine, so the 88.9% is optimistic.
- **Two cases fail on purpose** (documented known limits, `xfail` in `data/w12/eval_cases.json`): C07 (IDE says 2.4, pasted code needs 2.5) and C34 (a colloquial 429 question answered with junk).
- **Not done by a person:** the fresh-eyes review, the call from another squad's reviewer, the human re-labelling. The 10× limits are assumptions.

## Repo map

```
run_w12.py                       the entry point
src/w12_engine.py                Engine.ask: redact -> resolve version -> agent -> compose -> trace; the NAIVE / FIXED configurations (8 seam flags)
src/w12_agent.py w12_answer.py   the loop and the answer composer (deterministic stand-ins for the model)
src/w12_index.py w12_text.py     version-scoped RAG index; the shared stemmer
src/w12_versions.py w12_symbols.py w12_codecheck.py w12_redact.py w12_trace.py w12_mcp.py w12_llm.py
src/w12_eval.py w12_assertions.py w12_judge.py w12_trajectory.py w12_sweep.py w12_guards.py w12_retrieval_eval.py w12_loop.py w12_costs.py w12_report.py
mcp_servers/w12_sdk_docs_server.py   mcp_config.w12.json   reviewer_client.py
corpus/                          v2/ (2.x docs)  v3/ (3.0 additions + migration + changelog)  samples/  stackoverflow.jsonl  symbols.json
data/w12/                        eval_cases.json  hand_labels.json  trajectory_cases.json  retrieval_cases.json
output/w12/                      generated reports + the hand-written seams / weaknesses / architecture / demo / fresh_eyes
tests/test_w12.py                the tests (python -m pytest tests/test_w12.py)
```

Weeks 3–11 are untouched: `python -m pytest` runs their 138 tests plus the Week 12 ones.
