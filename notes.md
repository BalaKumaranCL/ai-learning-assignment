# Week 5 Notes — Error Analysis

## 0. Setup: why a trace log exists at all

This is a practice project with no real users, so there is no naturally-occurring "trace file that's grown past a thousand lines." [generate_traces.py](generate_traces.py) plays that week forward instead: it simulates realistic traffic (weighted question intents, paraphrased the way different developers actually ask, spread over 7 days, generation seed `20260915`) and runs every one of those 1200 questions through the real, unmodified Week 4 retriever (`RRFRetriever`) and a generation wrapper ([src/docs_assistant.py](src/docs_assistant.py)) — so every recorded output below is a real, computed result, not a hand-authored fake one. The result is [data/traces.jsonl](data/traces.jsonl), 1200 lines.

One realistic root cause is wired into the traffic simulation: the assistant is called from a web widget (always passes `sdk_version="v3"`) and an older Slack integration (never updated to pass any filter), so legacy v2 docs compete unfiltered on Slack traffic — this is what actually produces the DX lead's specific complaint, when it occurs.

One realistic logging gap is also wired in: traces from the first 5 of 7 days only recorded `{trace_id, timestamp, question, sdk_version_filter, answered, raw_output}`. Someone added `retriever_version`, `generator_version`, `min_score_threshold`, `retrieved` (top-3 chunk_ids + scores), `cited_chunk_id`, and `latency_ms` only from day 5 onward. That gap is real in the sample below, not simulated for effect after the fact.

## 1. Replay evidence

**Replay seed: `501`** (independent from the generation seed — an analyst doesn't control how the log was produced, only how they sample from it).

**Trace selected: `trace-00579`**

Original (as logged):
```json
{
  "raw_output": "## AuthConfig\n\n`AuthConfig` describes how the client should authenticate its requests.",
  "answered": true
}
```

Replayed (question + logged `sdk_version_filter` re-run through the current retriever + generator, nothing else supplied):
```json
{
  "replayed_raw_output": "## AuthConfig\n\n`AuthConfig` describes how the client should authenticate its requests.",
  "replayed_answered": true,
  "replayed_chunk_id": "authentication::structure::1",
  "replayed_score": 0.3959,
  "outputs_match": true
}
```

**Fields the original trace was missing** (this trace happened on day 2, before richer logging shipped): `retriever_version`, `generator_version`, `min_score_threshold`, `retrieved` (the actual top-3 chunk_ids/scores), `cited_chunk_id`, `latency_ms`. None of these can be reconstructed retroactively for this trace — replaying the question tells us what the CURRENT system does with it today, not what internal ranking actually happened at the time, since the corpus, retriever, and confidence logic could all have been different then. In this case the replayed output happens to match the original text exactly, which is reassuring but not proof nothing changed underneath it — a lucky trace to draw for a first replay check, and worth re-running on a few more once richer logging covers the whole window.

Full JSON: [output/w5/replay_evidence.json](output/w5/replay_evidence.json).

## 2. Seeded random sample (20 of 1200)

**Sample seed: `502`.** Trace IDs drawn: `trace-01035`, `trace-00744`, `trace-00345`, `trace-00720`, `trace-00347`, `trace-00873`, `trace-00083`, `trace-00776`, `trace-01036`, `trace-00159`, `trace-00505`, `trace-00653`, `trace-00403`, `trace-00221`, `trace-00658`, `trace-01102`, `trace-00478`, `trace-00504`, `trace-01173`, `trace-00131`.

Full trace content for all 20: [output/w5/sample_20.json](output/w5/sample_20.json).

## 3. Open coding — one sentence per trace, what I SAW (zero fixes applied)

1. **trace-01035** — Asked for `Client.send()`'s `timeout_ms` default and was refused; the top-ranked retrieved chunk was actually about `stream()`'s `chunk_size`, a different method entirely.
2. **trace-00744** — Answered "yes" but the cited text is only the one-sentence `AuthConfig` intro ("describes how the client should authenticate its requests"), which never actually states whether `api_key` is required.
3. **trace-00345** — Refused a plainly in-corpus question about `max_retries`'s default; this trace predates richer logging, so there's no retrieval detail to see why.
4. **trace-00720** — Answered correctly and completely with the full parameter table covering `headers`, `query_params`, and `body_encoding`.
5. **trace-00347** — Refused "what's the easiest way to authenticate a client"; no retrieval detail logged for this trace.
6. **trace-00873** — The identical question as #5, asked again on a later day with richer logging on: refused, even though the log shows the correct `AuthConfig` section was the retriever's own #1 result.
7. **trace-00083** — Refused "default body_encoding" even though a specific default value is directly documented; no retrieval detail available for this trace.
8. **trace-00776** — Refused a natural-language paraphrase of the exact `retry_backoff_ms` scenario named in the Week 4 assignment brief itself; no retrieval detail logged.
9. **trace-01036** — Answered "yes" but the cited text is just the bare page heading "# Streaming" with no actual content about how to get streaming responses.
10. **trace-00159** — Refused the literal wording of one of Week 3's own graded demo questions ("What parameter is required when creating an AuthConfig?"), which Week 3's own write-up reported as correctly answered.
11. **trace-00505** — Answered correctly and completely with the full exception table, clearly naming `AuthError`.
12. **trace-00653** — Correctly refused "How many concurrent requests does the SDK support?" — genuinely not documented anywhere in the corpus.
13. **trace-00403** — Refused the literal wording of one of Week 4's own golden-set questions about `max_retries`, despite that same phrasing being reported as a retrieval "hit" in Week 4's analysis.
14. **trace-00221** — Answered correctly and completely, explaining what `Client.close()` does and when to call it.
15. **trace-00658** — Refused "default chunk_size value" — a genuinely documented fact, but phrased too generically (no mention of "stream" or "Client") for the system to connect it; no filter was recorded on this trace.
16. **trace-01102** — Answered "yes" to "what does a non-200 status_code mean" but cited a short code EXAMPLE (`if response.status_code == 200`) instead of the actual explanatory sentence, which the log shows ranked one spot lower.
17. **trace-00478** — Answered correctly and completely, explaining the `X-Idempotency-Key` guarantee.
18. **trace-00504** — Refused "how often does the session token refresh by default" — `token_refresh_ms` is directly documented — with no retrieval detail available.
19. **trace-01173** — Refused the exact wording of a question used as a "hit" demo in earlier weeks; the log shows the correct parameter table chunk ranked #3, one place outside whatever pushed the top pick past it, but nothing cleared the confidence bar.
20. **trace-00131** — The same natural-language retry-timing paraphrase as #8, refused again on a different day — a second, independent instance of the same pattern.

## 4. Clustering into modes

See [taxonomy.md](taxonomy.md) for the ranked table. Method: each of the 20 sentences above was written first, purely describing what the trace showed; only after all 20 were written did I group them by what they had in common, rather than sorting traces into categories decided in advance.

## 5. Dated, falsifiable prediction

**Date: 2026-09-15**

**Mode to attack next week:** the over-refusal mode (dominant at 55% of this sample / ≈71.5% of the full 1200-trace log at the current `MIN_SCORE_THRESHOLD = 0.38`).

**Specific change:** lower `MIN_SCORE_THRESHOLD` from 0.38 to 0.25.

**Exact delta expected, both sides of the tradeoff (computed today by re-running the actual confidence function against all 1200 logged questions at candidate thresholds — not a guess):**
- The over-refusal mode drops from ≈71.5% (858/1200) to ≈27.2% (327/1200) of all traffic.
- Known cost: today's calibration shows this same change would flip roughly 34 of 86 (≈39.5%) genuinely out-of-corpus questions in the log from correctly-refused to wrongly-answered (today, at 0.38, that number is 0/86 — the current threshold has zero false positives on out-of-corpus questions, which is exactly why it's set so high).

**What would make this prediction wrong:** if, after actually shipping the threshold change and re-sampling a fresh 20 traces next week, the over-refusal mode's frequency in the new sample is not meaningfully lower than today's, or if the false-positive rate on out-of-corpus questions is far from the ≈39.5% predicted here — either result means a single global confidence threshold isn't the right lever, and a corpus-aware or per-intent signal is needed instead of just moving this one number.

**Committed to git:** commit `7f5a192992bb6cd97b6dcf96c46a6fc962d8742b` ("Add Week 5 error analysis: trace log, seeded sample, failure taxonomy"), dated 2026-09-15.

## 6. Why a public benchmark score would not have surfaced the top-3 modes

A public RAG benchmark scores against a fixed, curated set of question-answer pairs, so it would never include the casual, under-specified phrasings ("default max_retries value", "what's the easiest way to authenticate a client") that make up the bulk of the over-refusal mode here — a benchmark only ever asks the questions it was built to ask. Most retrieval benchmarks also score whether *any* relevant-looking chunk was retrieved, not whether the system actually surfaced a complete, usable answer to a real reader, so the shallow-citation mode (answering with a one-line section intro instead of the parameter table that actually has the value) would register as a retrieval hit and score perfectly fine. And a benchmark reports one aggregate accuracy number across many questions, which hides that a single global confidence threshold behaves completely differently for in-corpus versus out-of-corpus queries — our own calibration shows genuinely unanswerable questions max out at 0.376 confidence, a hair under the 0.38 cutoff — a tension invisible in a top-line score but obvious the moment you read individual traces one at a time.

## Bonus challenge (not attempted this round)

Sampling 10 more traces from a "curated demo set" and comparing top-mode frequency against the random sample was not done this round, to keep this submission focused on the required 100-point deliverable. Worth noting for later: Week 3's own three demo questions (retry_backoff_ms default, the code-example question, and the timeout exception question) were explicitly chosen in Week 3 because they scored well — exactly the "curated sample gives you frequencies that are pure fiction" trap this week's common-mistakes list warns about, and a natural, ready-made curated set to run the bonus against later.
