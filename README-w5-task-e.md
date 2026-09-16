# Week 5 Practical — Task Set E (practice implementation)

This extends Weeks 3-4 (see [README-w3-task-e.md](README-w3-task-e.md),
[README-w4-task-e.md](README-w4-task-e.md)). This week isn't about changing
the retriever at all — it's about reading real usage traces by hand and
building an honest, evidence-based list of what actually goes wrong.

## 1. Why does a trace log exist here, if this project has no real users?

The assignment assumes a live app whose trace file has "grown past a
thousand lines that nobody has read." This practice project has none of
that, so [generate_traces.py](generate_traces.py) plays that week forward:
it simulates realistic developer traffic — weighted question topics,
paraphrased the way different people actually ask, spread across 7 days —
and runs every one of those 1200 questions through the real, unmodified
Week 4 retriever. Every recorded output in
[data/traces.jsonl](data/traces.jsonl) is a real, computed result, not a
hand-written fake one.

## 2. What is "open coding," and why is it graded on doing nothing?

Open coding means reading each trace and writing one sentence describing
what you actually *saw* — not which bucket it belongs in, not what you'd
fix. The assignment gives zero points for polish and explicitly grades the
*zero code changes* during this step, because the moment you fix something
mid-read, every trace after that point is describing a different system —
your final taxonomy would quietly become fiction. See
[notes.md](notes.md) section 3 for the 20 real sentences.

## 3. Why random sampling instead of "the questions I remember breaking"?

A curated sample (the questions that already impressed people at a demo, or
the ones you know are broken) gives you frequencies that are pure fiction —
and frequency is half of how you decide what to fix first. This project
drew a **seeded** random sample (seed `502` — see
[notes.md](notes.md) section 2) so the sample is provably random, not
cherry-picked, and reproducible by anyone who runs the same seed against
the same log.

## 4. Why does one trace get "replayed," and what does "missing fields" mean?

Before trusting any conclusion drawn from a trace log, you need proof the
log actually captures enough to reconstruct what happened. [notes.md](notes.md)
section 1 picks one trace (seed `501`) and re-runs its exact recorded
question through the current system, showing the replayed output next to
the original. This project's logging also has a very real gap: for the
first 5 of 7 days, only `{question, sdk_version_filter, answered,
raw_output}` were recorded — no retrieved chunk_ids/scores, no
retriever/generator version, no latency. Most of the sampled traces predate
that gap being closed, which is exactly why several of the 20 open-coding
sentences say "no retrieval detail logged" instead of a diagnosis — a
missing field is a real, permanent hole in what can be known about that
trace, not something replay can retroactively fill in.

## 5. Why 5 failure modes and not, say, 2 or 10?

The assignment asks for 4-7 *named, legible* modes — few enough that a DX
lead can act on the list, many enough that "retrieval issue" isn't hiding
several different real problems inside one vague label. This project's 20
sentences were written first, purely descriptive; the 5 modes in
[taxonomy.md](taxonomy.md) were named only afterward, by grouping sentences
that turned out to share a real, visible pattern.

## 6. What did the numbers actually say, and why does it not match the DX lead's guess?

The DX lead's specific complaint (an outdated v2 default shown instead of
v3) is real but rare — 4 out of 1200 traces (≈0.3%). The mode that actually
dominates — refusing questions that are genuinely answerable in the docs —
made up 55% of the random sample (≈72% of the full log, at the confidence
threshold currently shipped). Nobody had complained about it, because a
refusal doesn't *look* broken the way a wrong version number does. See
[taxonomy.md](taxonomy.md) for the full ranked list and
[notes.md](notes.md) section 5 for the specific, falsifiable fix planned
for next week (with the real numeric tradeoff already calibrated against
this week's log, not guessed).

## 7. How to reproduce this

```bash
# from the repo root
pip install -r requirements.txt

python generate_traces.py     # writes data/traces.jsonl (1200 traces, seed 20260915)
python analyze_traces.py      # replay (seed 501) + seeded 20-sample (seed 502)
pytest tests/test_sampling.py tests/test_docs_assistant.py tests/test_tracing.py
pytest                        # full suite, Weeks 3-5 (52 tests)
```

## Project layout (additions on top of Weeks 3-4)

```
ai-learning-assignment/
├── data/traces.jsonl           1200 synthetic-but-genuinely-computed traces
├── src/
│   ├── docs_assistant.py       the "shipped" RRF + confidence-based answer/refuse logic
│   ├── tracing.py              trace schema, JSONL read/write, replay
│   └── sampling.py             seeded random sampling
├── output/w5/                  replay_evidence.json, sample_20.json (generated)
├── generate_traces.py          entry point: builds the trace log
├── analyze_traces.py           entry point: replay + seeded sample
├── taxonomy.md                 the required one-screen ranked failure taxonomy
├── notes.md                    all 20 open-coding sentences, seed values, replay evidence, prediction
└── tests/test_sampling.py, test_docs_assistant.py, test_tracing.py
```
