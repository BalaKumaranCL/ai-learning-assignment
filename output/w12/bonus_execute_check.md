# Bonus: stop judging code, start executing the check

Pin retrieval to the caller's version with a filter the code enforces (done: `ScopedIndex` + `assert_scoped`), then pipe **every emitted code sample** through parse -> imports -> symbols-exist-in-THIS-version -> run-against-a-stub-of-that-version (`src/w12_codecheck.py`).

The question: of the answers that passed the bar I used to accept, how many go red once "looks like code" stops counting? Three bars, because the answer depends on which one you used:

- **parses-only bar** (literally "looks like code"): the answer has code and every block `ast.parse`s. Nothing else.
- **looks-like-code + judge bar**: the above, and the judge calls it helpful. My judge also has a version-consistency rule (it rejects an answer whose sources name another major version), so it is already stricter than a naive judge.
- **old bar** (the Week 6/11 suite): the above, plus every cited page is the caller's major version and nothing on the old 4-name deprecation list is unflagged. It is stricter because the Week 6 page-version assertion already catches many wrong-version answers by their citation.

| System | Bar | Pass the bar (with code) | **Go red under execute-the-check** | % |
|---|---|---:|---:|---:|
| naive | parses only | 29 | **12** | 41.4% |
| naive | parses + judge | 6 | **1** | 16.7% |
| naive | old Week 6/11 bar | 6 | **1** | 16.7% |
| fixed | parses only | 27 | **0** | 0.0% |
| fixed | parses + judge | 27 | **0** | 0.0% |
| fixed | old Week 6/11 bar | 27 | **0** | 0.0% |

**The number the bonus asks for:** on the first integrated wiring, **12 of 29** answers that merely *looked like code* (they parse) fail the execute-the-check. Add my judge and it is 1 of 6; under the stricter Week 6/11 bar 1 of 6 — the stricter the old bar, the fewer wrong answers it let through, and the fewer it left to catch. After the fixes: 0 of 27.

Examples (naive, parses-only bar):

- C01 (trace `t_c4934cb741`): argument `api_key` of `Client` only exists from 2.5 (caller is on 2.4)
- C02 (trace `t_8bb9cb64a4`): argument `token` of `AuthConfig` was removed in 3.0 (not available in 3.0); use api_key
- C08 (trace `t_b05c00448a`): argument `api_key` of `Client` only exists from 2.5 (caller is on 2.4)
- C11 (trace `t_da0cac1f5a`): argument `api_key` of `Client` only exists from 2.5 (caller is on 2.4)
- C12 (trace `t_5aa0dd2f66`): argument `api_key` of `Client` only exists from 2.5 (caller is on 2.4)
- C13 (trace `t_161bc5f143`): argument `page` of `Client.list_messages` was removed in 3.0 (not available in 3.0); use cursor
