# Re-scored error taxonomy — the integrated system

The Week 5 taxonomy, re-scored on the integrated engine. **n = 38 cases** (35 hand-written questions, 1 case found by the version sweep, 2 corpus guards). A case can show more than one mode, so the percentages are "cases showing the mode / n", not a partition. Modes marked **NEW** exist only because components were joined: no part had them alone.

## A. First integrated run — every seam fix OFF (`naive`)

| # | Mode | NEW? | Cases | % of n | Severity | One trace id |
|---|---|---|---:|---:|---|---|
| 1 | **trace_lost_at_hop** — the server's spans do not carry the request's trace id | **NEW** | 36 | 94.7% | Blind spot: the request cannot be debugged end to end | `t_c4934cb741` (C01) |
| 2 | **wrong_version_answer** — the code (or the page it came from) does not belong to the caller's version | inherited | 31 | 81.6% | Ships code that fails at runtime in the caller's app | `t_c4934cb741` (C01) |
| 3 | **version_dropped_at_hop** — the resolved version never reached the MCP server, so it searched every version | **NEW** | 28 | 73.7% | Ships code that fails at runtime in the caller's app (root cause of the above) | `t_c4934cb741` (C01) |
| 4 | **version_misresolved** — the caller's version was resolved wrongly (or defaulted) | inherited | 5 | 13.2% | Ships code for the wrong version, with confidence | `t_8bb9cb64a4` (C02) |
| 5 | **secret_in_server_log** — a planted secret reached the MCP server's own log | **NEW** | 3 | 7.9% | Security incident: a pasted key is on disk in a log nobody redacts | `t_850af26628` (C30) |
| 6 | **lifecycle_not_surfaced** — a deprecation / removal was not stated, or an invented signature was written | inherited | 2 | 5.3% | Silent breakage later: the upgrade fails on something nobody warned about | `t_b05c00448a` (C08) |

Cases passing with every seam unfixed: **2 / 38**. (The 2 XFAIL cases are excluded from that count.)

## B. After the fixes — what is left (`fixed`)

| Mode | NEW? | Cases | % of n | Severity | One trace id | Status |
|---|---|---:|---:|---|---|---|
| **answer_missing_the_fact** | inherited | 2 (C07, C34) | 5.3% | Annoys: right version, wrong or empty answer | `t_466f1dac76` | documented known limit (XFAIL) — not fixed |

## C. Where each mode came from (what the ablation says fixed it)

| Mode | Fix that removes it | Evidence |
|---|---|---|
| version_dropped_at_hop | `inject_version` (+ `strict_server` as a second line) | see ablation.md |
| trace_lost_at_hop | `trace_hop` | trace_broken 36 -> 0 with that flag alone |
| secret_in_server_log | `redact_hop` | canary leaks 3/3 -> 0/3 with that flag alone |
| version_misresolved | `smart_resolve` | misresolved 5 -> 0 with that flag alone |
| wrong_version_answer | `minor_filter` + `inject_version` (scope) with `code_gate` as a safety net | 19 more cases fail if `minor_filter` is removed from the fixed system |
| lifecycle_not_surfaced / answer_missing_the_fact | retrieval + composer fixes made during the build (see seams.md); 2 cases remain | C07, C34 |
