# drill.md -- find the bad trace from logs alone

**Complaint (all I was given):** "a dev said it gave a code sample using a method we deprecated, some time last week." No trace id, no user, no package version.

## Result

| | |
|---|---|
| **Time-to-find, script clock** | **00:00** (3.0 ms for the whole hunt; `output/w11/hunt_v1.txt`) |
| **Time-to-find, human with stopwatch** | **NOT MEASURED -- to be filled in: `__:__`** |
| **Timed / verified by** | **NOT YET -- squadmate name + signature: `________`** |
| Found | trace `t_b3efb0c1df`, 2026-10-15 14:37:12, user `u-0417`, app `slack-bot`, prompt `docs_v1` |
| Under 5:00? | By the script clock yes; the human number is the one the rubric means and is still open |

**Read this before the number.** I (Claude) planted the bad answer, wrote the hunt, and ran it, so this is not a blind drill and no squadmate was involved. The script uses only the three clues the complaint gives (window, "code sample", "deprecated method") and never reads an id, user or version, but I knew what I was looking for. A 3 ms script run proves the logs *can* answer the question and shows which steps were needed; it says nothing about how long a person takes. To run the real drill, have a squadmate plant their own (command below), start a stopwatch, and use only the log file.

```
python plant_incident.py --out data/my_drill.jsonl --schema v1 --ts 2026-10-16T11:02:09 \
    --user u-0042 --app slack-bot --question "show me a code sample for streaming responses with Client.stream"
```

## The slice that found it

**Time window (2026-10-12..18) -> input type "code sample" -> deprecated-call pattern scanned inside the answer text.** In order (`hunt_v1.txt`):

| Step | lines in | lines out |
|---|---:|---:|
| Slice by time: last week | 1007 | 798 |
| Scan the **answer** text for a deprecated call (`.sendMessage(`, `.pollStream(`, `AuthConfig(token=`, `custom_headers`) | 798 | 69 |
| Drop callers who explicitly asked for v2 (their v2 sample is correct) | 69 | 1 |
| Drop answers that carry a migration note | 1 | **1** |

The step that did the work is the **output scan**. Searching only the question for a deprecated name is the tempting wrong move: it gives **36 wrong leads** in the same window (people *asking about* `sendMessage`, who got a correct migration answer or a refusal). The complaint describes the output, so the output has to be searchable.

## Honest audit: the log field that was missing

Even though the clock is fine, the logs as shipped (schema v1) force a slow path. What cost the steps:

- **`output_flags.deprecated_symbols_unflagged`** -- absent. The answer is free text, so I had to scan 798 answers with a hand-written regex and then write two exclusion rules (v2 caller, migration note) to get from 69 candidates to 1. A person doing this by eye or by `grep` is where the 5 minutes go. **This is the field that would have made the find instant.**
- `input_type` (code_sample / factual / migration) -- absent. I had to infer "code sample" from the content.
- `retrieved_sdk_versions` -- absent. The context ids are logged (good), but telling a v2 chunk from a v3 chunk means looking each id up in the corpus.

Wiring these in is the bonus, below.

## Diagnosis from the trace (`trace.json`): retrieval, not memory

- Context ids: `client_v2::archive::0`, `client_v2::archive::1`, `client::structure::1`. The answer **cites `client_v2::archive::0`**, an archived **v2** page, and its text is that page's sample verbatim (`client.sendMessage("hello")`, `AuthConfig(token=...)`).
- So the model did not hallucinate from pre-trained memory: retrieval served the archived v2 page and the answer quoted it. (Had the context held no sample, `docs_v1` would have written one "from memory" -- the `cited_chunk_id: null` shape. It is a different failure and not this one.)
- Why retrieval chose v2: the caller is `slack-bot`, which never sends an `sdk_version_filter`, so nothing restricted retrieval to v3, and the archived v2 sample out-ranked the v3 one (rank 1, TF-IDF confidence 0.478).
- Span timings: retrieval 43.8 ms, generation 902.6 ms, total 946.4 ms; 263 in / 54 out tokens; $0.0004187. Full detail in `trace.json`.

## Same root cause found elsewhere (side finding)

While building clean background traffic I found one more real instance: an unfiltered `What does Client.stream() return?` also returns the archived v2 streaming sample (`pollStream`, `AuthConfig(token=`). That pair is **quarantined out of the drill logs** so the drill has exactly one bad answer, not because it is unimportant. `docs_v2` fixes it too (checked: cites no deprecated symbol).

## Bonus: wire the drill shut, plant a second, beat the first time

Wired: schema v2 (`src/w11_logs.py`) computes `output_flags.deprecated_symbols_unflagged`, `input_type` and `retrieved_sdk_versions` **at write time**. Second bad answer planted with `python plant_incident.py --incident 2` (a *different* symbol, day and app: `pollStream`, 2026-10-17 09:05:41, `vscode-ext`, user `u-0233`; again by me, not a squadmate).

| | Hunt 1 (schema v1) | Hunt 2 (schema v2, wired) |
|---|---|---|
| Script clock | 3.0 ms | 0.5 ms |
| Steps | 4 (1 time slice + regex scan + 2 hand-written exclusion rules) | **2** (time slice + one field) |
| Lines to judge after the scan | 69 | **1** |
| Found | `t_b3efb0c1df` | `t_f5d1279f52` |

**The one field that closed the gap: `output_flags.deprecated_symbols_unflagged`.** Filtering `!= []` returns the bad trace directly, with no regex, no exclusion rules and no judgement calls. The honest comparison is the 4-to-2 steps and 69-to-1 lines; the millisecond gap on 1,007 rows is not a meaningful measure, and hunt 2 was not timed by a human either. Reproduce: `python run_w11_hunt.py --indexed data/w11_prod_logs_v2.jsonl`.
