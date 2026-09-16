# Week 6 Practical — Task Set E (practice implementation)

Extends Weeks 3-5 (see [README-w3-task-e.md](README-w3-task-e.md),
[README-w4-task-e.md](README-w4-task-e.md),
[README-w5-task-e.md](README-w5-task-e.md)). This week isn't about the
retriever or the traces — it's about the *judge*: the thing that scores
whether an answer is good, which nobody has ever checked against a human.

## 1. Why does this project need a fake "LLM judge"?

The assignment assumes a real LLM scores answer helpfulness. This project
has never used an LLM anywhere — [src/generator.py](src/generator.py) and
[src/docs_assistant.py](src/docs_assistant.py) are explicit, documented
stand-ins, not API calls. [src/judge.py](src/judge.py) follows the exact
same pattern: a small, honest, deliberately-imperfect heuristic playing the
role of the untrusted judge. See [judge_v1.txt](judge_v1.txt) for exactly
what it checks.

## 2. What does "blind" labeling actually mean here, and how is it proven?

Blind means the 25+ hand labels in [labels_25.json](labels_25.json) were
written having seen only the question and answer text — never a judge's
verdict, because at the moment they were written, **no judge code existed
in this repository at all**. That's provable, not just claimed: commit
`443de8f` added the labels; `src/judge.py` doesn't appear anywhere in this
repo's history before it. See [notes_w6.md](notes_w6.md) section 2.

## 3. Why move some criteria out of the judge and into plain code?

Because a parser and a metadata lookup settle some questions for free and
never have an off day — paying a heuristic (or a real LLM) to guess whether
a citation's SDK version matches the request is wasteful when it's a direct
lookup. [src/assertions.py](src/assertions.py) has 3 such checks; the judge
handles only what's left: the genuinely fuzzy "is this actually helpful"
call. See [notes_w6.md](notes_w6.md) section 1 for the full split, and
section 4 for a real bug found in one of these assertions (fixed on the
spot, since an assertion has no excuse to be probabilistic).

## 4. What did validating the judge actually find?

`judge_v1` agreed with the blind human labels on 74.2% (23/31) of cases —
not because it's random, but because it has one specific, describable blind
spot: it can't tell a fluent, complete-looking WRONG answer (citing the
legacy v2 default for a version-unscoped question) from a genuinely correct
one. Two real disagreements were used to design `judge_v2` — agreement rose
to only 77.4% (24/31), not the 84% predicted beforehand, because the fix
for the wrong-version case had a real logic bug (it only checked when a
filter was explicitly requested — but the actual failure happens precisely
when no filter is requested at all). Full disagreement analysis, and where
the prediction was wrong, in [notes_w6.md](notes_w6.md) sections 4-5.

## 5. How to reproduce this

```bash
# from the repo root
pip install -r requirements.txt

python build_eval_set.py      # writes data/eval_set.json (31 tagged cases)
python run_eval.py            # the one command: assertions + judge_v2, pass rate by mode
pytest tests/test_assertions.py tests/test_judge.py
pytest                        # full suite, Weeks 3-6
```

## Project layout (additions on top of Weeks 3-5)

```
ai-learning-assignment/
├── data/eval_set.json      31 cases, each tagged with a Week 5 taxonomy mode
├── src/
│   ├── assertions.py        3 deterministic, code-only checks
│   └── judge.py             judge_v1 (naive) and judge_v2 (2 targeted fixes) heuristics
├── build_eval_set.py         entry point: builds the eval set
├── run_eval.py                entry point: the one-command eval (pass rate by mode)
├── labels_25.json             31 blind hand labels, committed before judge.py existed
├── judge_v1.txt, judge_v2.txt the judge's plain-English rules, each version
├── prediction.txt              written before designing judge_v2
├── notes_w6.md                 agreement numbers, disagreement analysis, prediction scored
└── tests/test_assertions.py, test_judge.py
```
