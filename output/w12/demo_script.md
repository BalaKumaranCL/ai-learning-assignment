# 10-minute demo script — four parts, to the clock

Numbers below are from the run of 2026-11-02 (`python run_w12.py`, ~2 min); they are regenerated in `EVAL_REPORT.md` every time. **Say the numbers from that file on the day, not from this one.**

Set up once, before the clock starts: `cd` to the repo, activate the venv, run `python run_w12.py` so `output/w12/` is fresh. Have `output/w12/taxonomy.md`, `EVAL_REPORT.md` and `closed_loop.md` open in tabs.

---

## 0:00 – 0:30  Frame it (say)

> "Nine thousand integrators, two live versions: 2.x and 3.0. The expensive ticket starts 'I copied this from your docs'. So this system answers against the caller's actual version, says plainly when a method is gone, and the number I care about is not answer rate — it's how many answers contain code that would actually run."

## 0:30 – 3:30  Part 1 — a real run (live)

```
python run_w12.py ask "How do I paginate through my messages?" --version 2.4
```
Point at, in this order:
1. First line: **"Answering for Acme SDK 2.4 (version taken from your IDE's request metadata)"** — and in the span table, `resolve_version` comes *before* the first `tool:` span. Version first, retrieval second.
2. The sample uses `page=` / `per_page=` — the 2.4 API. Not the 3.0 `cursor`.
3. **Sources:** every link names its version: *"Acme SDK 2.x"*.
4. The **unasked notice**: `Client.list_messages(per_page=...)` is deprecated from 2.6 and removed in 3.0. Nobody asked.
5. Spans: one trace id on the engine spans **and** the server spans (the MCP hop).

```
python run_w12.py ask "Does client.pollStream still work in 3.0?" --version 2.4
```
Point at: **"`Client.pollStream` no longer exists in 3.0"** — plain, with the migration, and a sample for `Client.stream` that was verified against **2.4**, so they can switch before upgrading. (Sample shows the *replacement*, not the removed method — I found that by eye, not by a test: seam S18.)

```
python run_w12.py ask "How do I use client.query() to search my messages?" --version 3.0
```
Point at: `client.query()` **never existed in any release**; it does not invent a signature.

*(Don't demo "how do I authenticate?" — it is the question where 2.x and 3.0 almost agree. Here they don't (token vs api_key), but it proves nothing.)*

## 3:30 – 6:00  Part 2 — the failures I found

```
python run_w12.py ask "How do I send a message?" --version 2.4 --naive
```
Point at: the header says **2.4**, the code is the **3.0 client** (`Client(api_key=...)`, which does not exist before 2.5), the source is *"Acme SDK 3.0"*. It imports cleanly and fails in the caller's app. The trace is in `trace_example.md` (compare its two halves: the `naive` server spans carry no trace id).

Open `taxonomy.md` — first integrated run, every seam fix off, n = 38:
- **trace_lost_at_hop** — NEW, 94.7% — the server logged under a trace id nobody can join to the request.
- **wrong_version_answer** — 81.6%.
- **version_dropped_at_hop** — NEW, 73.7% — the version never crossed the MCP hop; the server searched *every* version.
- version_misresolved 13.2% · **secret_in_server_log** — NEW, 7.9% (3 of 3 planted keys on disk in a log nobody redacts) · lifecycle_not_surfaced 5.3%.

Say: "Three of the seven modes are **new** — no part had them alone. Week 9's server treats 'no version' as 'search everything'; Week 9's host only learns a version from the question text; Week 11 fixed its own incident by defaulting to v3, which is the wrong answer for the 40% on v2."

My three weaknesses, written **before** the first run (`weaknesses.md`, dated 2026-11-02 — it was not Wednesday; I'm not going to claim it was): (1) colloquial phrasing misses, (2) the symbol table is the only ground truth and I wrote it, (3) I believe the version I'm told.
And what remains after the fixes: **C07, C34** — both documented, neither fixed.

## 6:00 – 8:00  Part 3 — a number that moved

Open `EVAL_REPORT.md`.
- **Wrong-version code-sample rate: 12/29 = 41.4% → 0/27 = 0.0%.** n = code-bearing answers out of 36 questions. "Wrong" means: fails parse, imports, symbols-exist-in-the-caller's-version, or run. It is a deterministic check, not a judge.
- Honest footnote: "before" is every seam unfixed at once, so 41% is an upper bound; `ablation.md` says which fix is worth what (`minor_filter` alone is worth 19 cases).
- **Judge agreement with my hand labels: 32/36 = 88.9%** (bar 85%). It misses the same junk answers I did (C07, C21, C34) and marks a correct refusal (C36) unhelpful. The pass/fail verdicts come from assertions, not the judge.
- **What the suite does not measure at all** (one sentence): *"Everything with a model in it — planner, composer, judge — is a stand-in, and 'the code runs' means 'runs against a stub of my own symbol table', so none of this tells you how a real model on the real package would behave."*
- Bonus: `bonus_execute_check.md` — of the naive answers that merely *parse*, **12 of 29** fail the execute-the-check.

## 8:00 – 10:00  Part 4 — what's next

```
python run_w12.py loop
```
- The case that now guards a failure: **C36** — a 2.1 caller asks for a custom header; nothing in 2.1 can take one. Found by the **version sweep** (66 requests: 6 questions × every version), not by any of my 35 hand-written cases. RED → fix → GREEN, **0 regressions**.
- **Cost per question: $0.00397** (modelled; tokens and calls measured): planner 61%, composer 36%, tools 2.5%.
- **What breaks first at 10×** (`tenx.md`): the **monthly budget at 6.7×** (assumed $2,000/month), then input tokens at 13×, requests/min at 31×; the MCP server at ~1,400×. And something worse than a scaling limit: **p99 is 8.1 s against a 3 s in-IDE target already at 1×** — 4 sequential model calls per question. Fix #1 (return lifecycle inside the search result, not a separate lap): −15% cost, −0.6 s. Not done.

> "A flawless demo is a red flag. What failed: the first wiring failed 34 of 36 cases; after the fixes two cases still fail on purpose — C34, a 429 question answered with an auth paragraph at full confidence, and C07, a caller whose IDE and pasted code disagree — and the trajectory eval found a right answer reached by an unsafe path (T10)."

---

## Hostile questions — answers with numbers

1. **"Does your retriever FILTER on version?"** Yes: one RRF index per major version, a range filter by minor, and `assert_scoped` raises if anything out of range slips through. The eval case is the whole suite (`scope_respected` on every case) plus the 66-request sweep: 0 failing. Take the filter's minor-range part out and **19 of 36 cases fail** (`ablation.md`).
2. **"Does anything check that the code parses, imports, and the methods exist in that version?"** Yes — `src/w12_codecheck.py`, on every emitted sample: parse, imports, symbols, run against a stub. Run it on the old "looks like code" bar and 12 of 29 naive answers go red. Caveat: the stub is generated from my own table (weakness 2).
3. **"Why is a 2019 Stack Overflow page in your corpus?"** Dropping it costs **0.0 pt of hit@3** (91.7% vs 91.7%, n=12); keeping it as ordinary content puts a dead API at rank 1 for **9 of 12** questions. It stays out of the served index (`so_ablation.md`); its only job is phrasing, and on 12 questions that job earned nothing — I wouldn't claim it helps.
4. **"v3.1 ships next month with two deprecations. What does re-indexing cost and which case goes red?"** 50 ms to rebuild; guard **G02** goes red (symbol table vs changelog) and **no question case does** — which is exactly why G02 exists (`drill_v31.md`).
5. **"Faithfulness is 91% — which 9%?"** I don't report faithfulness: it would be by-construction on a deterministic composer. What I report: 0 of 27 emitted samples fail the version check; the 2 known failures are a junk answer on a colloquial question (C34) and a caller whose IDE and code disagree (C07) — neither is in the breaking-change set; the weak spot there is the symbol sweep (T10), which missed `page=`.
