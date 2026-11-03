# Ablation — which seam fix removes which failure

Same 38-case suite, run once per configuration (judge off: assertions only). `wrong-version code` = answers whose code fails the caller's version check / answers that contain code.

| Configuration | Pass | Fail | XFAIL | Wrong-version code | Trace broken | Secret leaked | Misresolved | Failing cases |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| naive (all 8 off) | 2 | 34 | 2 | 12/29 (41.4%) | 36 | 3/3 | 5 | C01, C02, C03, C04, C05, C06, C08, C09 … |
| only smart_resolve ON | 3 | 33 | 2 | 12/28 (42.9%) | 35 | 3/3 | 0 | C01, C02, C03, C04, C06, C08, C09, C10 … |
| only inject_version ON | 2 | 34 | 2 | 8/29 (27.6%) | 36 | 3/3 | 5 | C01, C02, C03, C04, C05, C06, C08, C09 … |
| only strict_server ON | 2 | 34 | 2 | 9/29 (31.0%) | 36 | 3/3 | 5 | C01, C02, C03, C04, C05, C06, C08, C09 … |
| only minor_filter ON | 2 | 34 | 2 | 13/29 (44.8%) | 36 | 3/3 | 5 | C01, C02, C03, C04, C05, C06, C08, C09 … |
| only trace_hop ON | 3 | 33 | 2 | 12/29 (41.4%) | 0 | 3/3 | 5 | C01, C02, C03, C04, C05, C06, C08, C09 … |
| only redact_hop ON | 2 | 34 | 2 | 12/29 (41.4%) | 36 | 0/3 | 5 | C01, C02, C03, C04, C05, C06, C08, C09 … |
| only code_gate ON | 2 | 34 | 2 | 0/23 (0.0%) | 36 | 3/3 | 5 | C01, C02, C03, C04, C05, C06, C08, C09 … |
| only relevance_floor ON | 2 | 34 | 2 | 12/29 (41.4%) | 36 | 3/3 | 5 | C01, C02, C03, C04, C05, C06, C08, C09 … |
| fixed (all 8 on) | 36 | 0 | 2 | 0/27 (0.0%) | 0 | 0/3 | 0 |  |
| fixed, smart_resolve OFF | 31 | 5 | 2 | 0/28 (0.0%) | 0 | 0/3 | 5 | C02, C03, C04, C05, C06 |
| fixed, inject_version OFF | 33 | 3 | 2 | 0/25 (0.0%) | 0 | 0/3 | 0 | C18, C19, C20 |
| fixed, strict_server OFF | 36 | 0 | 2 | 0/27 (0.0%) | 0 | 0/3 | 0 |  |
| fixed, minor_filter OFF | 17 | 19 | 2 | 0/27 (0.0%) | 0 | 0/3 | 0 | C01, C02, C03, C06, C08, C09, C10, C11 … |
| fixed, trace_hop OFF | 3 | 33 | 2 | 0/27 (0.0%) | 35 | 0/3 | 0 | C01, C02, C03, C04, C06, C08, C09, C10 … |
| fixed, redact_hop OFF | 33 | 3 | 2 | 0/27 (0.0%) | 0 | 3/3 | 0 | C30, C31, C32 |
| fixed, code_gate OFF | 36 | 0 | 2 | 0/27 (0.0%) | 0 | 0/3 | 0 |  |
| fixed, relevance_floor OFF | 35 | 1 | 2 | 0/28 (0.0%) | 0 | 0/3 | 0 | C36 |

What it says (read off the table, not argued):

- **No single fix rescues the naive system**: the suite is passed only when all the seams are closed, because a case fails if *any* assertion fails.
- **`minor_filter` carries the most weight**: with it OFF in the otherwise-fixed system, 19 of 36 cases fail (a 2.4 caller gets sections that only exist from 2.5/2.6).
- **`trace_hop`, `redact_hop` and `smart_resolve` each fix exactly one named failure**: trace broken 36 -> 0, secret leaks 3/3 -> 0/3, misresolved 5 -> 0.
- **`strict_server` and `code_gate` add nothing on this suite** when the others are on: with either one OFF the fixed system still passes everything. They are second lines of defence (the server refuses a call with no version; the gate catches a sample the lint missed). Reporting them as "fixes" would be dishonest; they are insurance. `code_gate` alone turns a wrong-version snippet into *no snippet* (0/23 wrong, but only 2 passes of 36): safe, not helpful.
- `relevance_floor` fixes exactly one case (C36), the one the version sweep found.
