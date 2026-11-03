# The closed failure -> test loop (live, on the integrated system)

1. **The failure.** The version sweep (`src/w12_sweep.py`: 6 core questions x every version 2.0-2.9 and 3.0 = 66 requests) found that a **2.0 / 2.1 caller asking how to add a custom header** was handed a valid but unrelated `send()` sample. Nothing in 2.0-2.1 can take a header (`RequestOptions` only goes to `send()`, added in 2.2). None of my 35 hand-written cases covered it.
2. **The test.** Case **C36** (`data/w12/eval_cases.json`): version 2.1, "How do I add a custom header to a request?", expected: a plain refusal and **no code**.
3. **RED** — the system as it shipped (`relevance_floor` OFF): **35 pass / 1 fail / 2 xfail of 38**. C36 fails: expected_content: missing ["can't answer"]; answered_as_expected: should have declined: nothing in this version's docs answers the question
4. **The fix.** `relevance_floor`: never offer a code sample that shares no content word with the question (matched on the sample's title and tags, not its body — generic words like "request" in a `print()` string had made a timeout sample 'relevant' to a headers question), plus corpus fixes (two doc sections wrongly tagged valid from 2.0).
5. **GREEN** — **36 pass / 0 fail / 2 xfail of 38**. Fixed: C36. **Regressions (passed before, not now): none.**
6. **The sweep, before -> after:** 2 failing of 66 (S-headers-2.0, S-headers-2.1) -> 0 failing.

Why it is *permanent*: C36 is in the suite that `python run_w12.py` runs every time. Re-run the RED half yourself: `python run_w12.py loop`.
