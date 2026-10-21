# deploy.md -- prompt version bump, canary and rollback

**Version bump: `docs_v1` -> `docs_v2`** (`ACTIVE_PROMPT_VERSION` in `src/w11_service.py`; every trace records the version that answered it).

What `docs_v2` changes (all four listed in `FEATURES["docs_v2"]`):
1. Retrieval: callers who send no `sdk_version_filter` get v3 docs, unless the question itself asks about v2/legacy.
2. Retrieval: for code-sample requests, "give me a code sample for X" is searched as "X" and the context is 5 chunks deep (sample chunks rank below prose chunks).
3. Generation: never write a sample "from memory"; if the context has none, say so.
4. Tools: every code sample goes through `check_deprecation` before it is returned.

## The two lines

1. **Canary:** serve `docs_v2` to 5% of users (hash on `user_id`) for 24 h, then 25%, then 100%, advancing only while `output_flags.deprecated_symbols_unflagged` stays empty in canary logs, answered-rate stays within 10 points of the replay figure (52.5%), and cost/query stays within +30% of the `docs_v1` baseline (replay predicts +22.7%).
2. **Rollback:** set `ACTIVE_PROMPT_VERSION` back to `docs_v1` (a one-line revert, no data migration; `docs_v1` behaviour is pinned by `python run_w11_suite.py --prompt docs_v1`), triggered by any unflagged deprecated hit, a p99 breach, or an answered-rate drop beyond the band -- knowing a rollback re-opens this incident, so a rollback must come with a same-day follow-up.

Status: this is a **plan**. The 5%/25%/100% split is not implemented in code (the service takes one active version), and the thresholds above are my proposals, not values anyone signed off.

## Evidence the fix is safe to ship (pre-canary)

- Suite, live, 33 cases: `docs_v1` 30/33 (RED) -> `docs_v2` 33/33 (GREEN). No case went from pass to fail. See `suite_red.txt`, `suite_green.txt`.
- Replay of last week's 798 real requests: unflagged deprecated answers 1 -> 0; answered-rate 44.7% -> 52.5%; 83 answers changed. See `replay_summary.json`.
