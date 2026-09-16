# Docs Assistant — Failure Taxonomy (Week 5)

Sample: 20 traces, seeded random draw (seed `502`) from 1200 traces logged over the last 7 days. Full evidence in [notes.md](notes.md).

| Mode | Count | % of 20 | Severity | Example trace_id |
|---|---:|---:|---|---|
| **Refuses a fully in-corpus question and the log has no retrieval detail to say why** | 9 | 45% | Merely annoys the reader | `trace-00345` |
| **Answers, but cites a chunk too shallow/generic to actually contain the answer** | 2 | 10% | Merely annoys the reader | `trace-00744` |
| **Declines to answer even though the log shows the right section was already in the top results** | 2 | 10% | Merely annoys the reader (but directly fixable — retrieval already succeeded) | `trace-00873` |
| **Retrieval finds the wrong feature entirely for a short/casual phrasing** | 1 | 5% | Ships broken code to a user's repo, if confidence had cleared the bar this time | `trace-01035` |
| **Answers, but cites a neighboring/tangential chunk instead of the one that explains the concept asked about** | 1 | 5% | Merely annoys the reader | `trace-01102` |

Not failures, tallied for context: correctly answered in full (4/20, 20%), correctly refused a genuinely out-of-corpus question (1/20, 5%).

**Note on the DX lead's original complaint ("sometimes gives outdated code"):** that specific symptom — citing the legacy v2 default instead of v3 — exists in the full 1200-trace log (4 instances, ≈0.3%) but did not land in this random sample; it's real but rare. The mode that actually dominates (45%+10%=55% of this sample, ≈72% of the full log at the current confidence threshold) is one nobody had complained about: over-refusal. A refusal doesn't *look* broken the way a wrong version number does, so it never got reported — exactly the gap this exercise exists to close.
