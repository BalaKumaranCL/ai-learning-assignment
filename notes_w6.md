# Week 6 Notes — Judge Validation

## 0. Why the judge is a heuristic, not a real LLM

This project has never called an LLM (see [src/generator.py](src/generator.py),
[src/docs_assistant.py](src/docs_assistant.py) docstrings — "no API key
needed, it's all local math"). Week 6 assumes "an LLM judge nobody has
checked against a human." Consistent with every prior week's practice
stand-ins, [src/judge.py](src/judge.py) is a small, explicit, documented
heuristic playing that role — see [judge_v1.txt](judge_v1.txt) /
[judge_v2.txt](judge_v2.txt) for its plain-English rules.

## 1. Eval set and assertion/judge split

[data/eval_set.json](data/eval_set.json) — **31 cases** (spec requires
25+), built by [build_eval_set.py](build_eval_set.py): 20 reuse Week 5's
seeded random sample verbatim (same questions, freshly re-answered), 5 more
are real trace_ids pulled from the full 1200-trace log, 6 are fresh
canonical-phrasing controls. **5 cases are explicit regressions** replayed
verbatim from real failed traces (spec requires 2+): `E01`
(`trace-01035`), `E02` (`trace-00744`), `E16` (`trace-01102`), `E21`
(`trace-00954`), `E22` (`trace-01128`). Every case is tagged with its Week
5 taxonomy mode.

**Assertions vs judged criteria: 3 deterministic assertions, 1 judged
criterion.** [src/assertions.py](src/assertions.py):
1. `no_unflagged_version_mismatch` — the cited chunk's sdk_version must be
   consistent with the request (see section 4 below for a real bug found
   and fixed in this exact assertion).
2. `code_sample_parses` — any ```python fence in the answer must be valid
   Python (`ast.parse`).
3. `cited_chunk_exists` — the cited chunk_id must actually exist in the
   corpus.

These were picked because a parser and a metadata lookup settle them for
free, matching the assignment's own examples (code parses, endpoint exists
in spec, version stated) adapted to this project's actual corpus — none of
these need a judge's opinion, and none are part of the judge's prompt.

**Judge's single judged criterion:** "Is this answer helpful?" (Y/N) — see
[judge_v1.txt](judge_v1.txt).

## 2. Blind protocol — proof of ordering

[labels_25.json](labels_25.json) was committed in commit `443de8f` at
**2026-09-16T15:05:41+05:30**, containing 31 hand labels on the single
binary criterion, read blind (question + answer text only — no
`taxonomy_mode`/`source` fields shown). **`src/judge.py` did not exist in
the repository at that commit** — `git log --diff-filter=A -- src/judge.py`
confirms `src/judge.py` was first added in a later commit. The labels
structurally cannot have been influenced by a judge that didn't exist yet.

## 3. Agreement before → after

Computed by comparing `judge_v1`/`judge_v2` output against `labels_25.json`
for all 31 cases:

| | Agreement |
|---|---:|
| **Before** (judge_v1) | **74.2%** (23/31) |
| **After** (judge_v2) | **77.4%** (24/31) |

## 4. Prediction, scored honestly against the outcome

**[prediction.txt](prediction.txt)**, written before judge_v2 existed:
> Using E21 (wrong-version) and E16 (tangential citation) as the two
> few-shot disagreement examples driving the v2 rewrite: I predict that
> fixing cluster (a) alone will raise agreement from 74.2% to about 84%
> (26/31), while leaving cluster (b)'s 4 cases (E12, E23, E30, E31)
> untouched.

**What actually happened:** agreement rose to 77.4% (24/31), not 84%
(26/31). **The prediction was wrong, and the second half of it (the
untouched cluster) was right.**

**Where it was wrong, specifically:** judge_v2's new version-mismatch rule
was written as `if sdk_version_filter is not None and cited version !=
filter → N`. E21 and E22 — the two wrong-version regression cases the rule
was built to catch — both have `sdk_version_filter = None` (no filter was
ever requested; that's *why* the legacy v2 chunk won in the first place).
The rule's own guard clause skips the check exactly when no filter is
present, which is exactly the situation E21/E22 are in — so the rule
**never fires on the cases it was designed for.** Only the second new rule
(the Example-anchor rule, fixing `E16`) actually landed. Net effect: +1
case fixed (`E16`), not +3, for +3.2 points instead of the predicted +9.8.

**Where it was right:** cluster (b) — `E12`, `E23`, `E30`, `E31`, all
correctly-refused out-of-corpus questions that judge_v2 still marks
"unhelpful" — remained untouched exactly as predicted, because neither new
rule addresses judge_v1's blanket "refused → N" rule at all.

**A related, more serious bug found while checking this:** the
deterministic assertion `no_unflagged_version_mismatch` had the identical
guard-clause flaw — it also skipped checking when no filter was requested,
meaning it silently PASSED `E21`/`E22` even though they're the clearest
wrong-version case in the whole eval set. Unlike the judge (a
work-in-progress heuristic, allowed to be imperfect this week), an
assertion is supposed to be reliably correct, so this one was fixed
directly (see [src/assertions.py](src/assertions.py) docstring on
`no_unflagged_version_mismatch`) rather than left as a second "known gap."
The judge's version-mismatch rule was deliberately left with its original
bug, since `agreement_after` above reports what was actually tested this
cycle — fixing it properly is the natural target for a v3 next week.

## 5. Two disagreements read in full, verdict on who was right

**`E21`** — *"what's the default retry_backoff_ms"* (no `sdk_version_filter`).
Answer: *"In the legacy v2 SDK, Client.send() accepts a retry_backoff_ms
parameter. The default value of retry_backoff_ms in v2 is 500 milliseconds
between retries."* `judge_v1` said **Y** (86 characters, substantial text).
Human said **N**. **Human was right**: this is the exact "v2 endpoints keep
getting recommended to v3 users" risk named in this week's problem
statement — a fluent, complete-looking answer that is factually the wrong
version's default. `judge_v1` cannot be right here by construction: it
never looks at *which* SDK version it's citing, only whether text came
back at all.

**`E16`** — *"What does a status_code other than 200 mean on a Response?"*
Answer: a code fence showing `if response.status_code == 200: print(...)`.
`judge_v1` said **Y** (a real, substantial code block). Human said **N**.
**Human was right**: the snippet is genuine, valid content, but it's an
*example of checking* status 200 — it never states what a *non*-200 code
means, which is literally what was asked. `judge_v1` cannot distinguish
"long and topically adjacent" from "actually answers the specific
question," because it never looks past text length.

## 6. One-command eval

```
$ python run_eval.py
```

Full terminal output:

```
Eval set: 31 cases, 3 deterministic assertions, 1 judged criterion (judge_v2)

Mode                                     Pass  Total    Rate
------------------------------------------------------------
over_refusal_no_detail                      0     13    0.0%
correct_complete                            6      6  100.0%
correctly_refused_oos                       0      4    0.0%
shallow_citation                            1      2   50.0%
declines_despite_correct_retrieval          0      2    0.0%
wrong_version                               0      2    0.0%
wrong_feature_retrieval                     0      1    0.0%
tangential_citation                         0      1    0.0%
------------------------------------------------------------
TOTAL                                       7     31   22.6%

Regression cases (replayed verbatim from real failed traces):
  E01 (w5_sample:trace-01035): FAIL
  E02 (w5_sample:trace-00744): PASS
  E16 (w5_sample:trace-01102): FAIL
  E21 (full_log:trace-00954): FAIL
  E22 (full_log:trace-01128): FAIL

Note: correctly_refused_oos scores 0% here on purpose -- judge_v2 still marks
every refusal 'not helpful' regardless of whether the refusal was correct.
That is a known, documented, still-open gap, not a bug in this report.
```

The average (22.6%) hides exactly what the common-mistakes list warns
about: `correct_complete` is a clean 100%, `wrong_version` is now correctly
caught at 0% (post assertion fix) — a single top-line number would bury
both the win and the version-confusion regression inside one blended
figure.

## Bonus challenge (RAGAS faithfulness/context precision)

Not attempted this round, to keep this submission focused on the required
100-point deliverable — this project has no LLM to generate free-text
answers for RAGAS's faithfulness metric to score in the first place (every
answer here is a verbatim chunk quote, not a synthesized claim), so
applying it meaningfully would require first building a real
answer-synthesis step, which is out of scope for this week.
