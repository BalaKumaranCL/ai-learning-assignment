# Seam list (Week 12) — written as I found them, not rewritten afterwards

A **seam** is a place where two pieces that each work on their own disagree once they are joined.
Entries are in the order I hit them. Only the `Status` line is updated at the end (the brief asks each seam to be marked fixed / accepted / ran-out-of-time). Everything above the status line is the original wording.

Date started: 2026-11-02. The first block (S1–S6) was found by **reading** the Week 3–11 code before writing any Week 12 code. Later blocks were found by **running** things; each says so.

---

## Found while reading the old weeks (before wiring anything)

### S1 — The single command does not run on the default Python
`python -c "import sklearn"` fails on the machine's default Python (3.15). Only `.venv-mcp` (3.11) has scikit-learn, rank_bm25 and the MCP SDK. Week 11's README said "needs no venv"; that is no longer true here.
Status: **fixed** — `run_w12.py` checks its imports first and prints a one-line fix (verified by running it on the default Python, which has neither scikit-learn nor mcp); the README says to create a venv and `pip install -r requirements.txt`.

### S2 — Week 9's docs server treats "no version" as "search everything"
`mcp_servers/docs_search_server.py` documents `sdk_version` as optional: "omit it to search everything". Fine for a demo; for Week 12 it means any caller that forgets to pass a version silently gets v2 *and* v3 mixed together.
Status: **fixed** — the new server refuses a call with no version (`VERSION_REQUIRED`) by default. Week 9's lenient behaviour is kept behind `W12_VERSION_POLICY=lenient` so the before could be MEASURED (ablation: with the server strict but nothing else, wrong-version code is 9/29 instead of 12/29). With every other fix on it adds nothing on this suite: it is insurance.

### S3 — Week 9's host fills the version from the question text only
`src/mcp_llm_sim.py::extract_slots` only sets `sdk_version` if the question itself contains `v2`/`v3`. A caller whose IDE says "2.4" but whose question says nothing about versions sends no version at all (see S2). Neither piece is wrong alone.
Status: **fixed** — `inject_version`: the agent puts the resolved version into each tool call from the tool's own input schema (ablation: wrong-version code 12/29 -> 8/29 alone; with it OFF in the fixed system, C18-C20 fail).

### S4 — Week 11's fix for "v2 chunk served to a v3 caller" is the exact opposite bug here
`w11_service.py` fixed its incident by defaulting callers with no version to **v3**. In Week 12 ~40% of callers are on v2, so the "fix" hands them a v3 snippet — the headline failure in the brief.
Status: **fixed** — no silent default. The resolver tries 5 sources and otherwise ASKS (C05). The Week 11 behaviour is still in the `naive` configuration, where it produced the 5 misresolved cases.

### S5 — Week 4's version filter only knows "v2" or "v3", not "2.4"
`TfidfRetriever` filters on an exact `sdk_version` string. There is no minor version, so a 2.4 caller can be served a section that only exists from 2.6.
Status: **fixed** — `valid_from` / `valid_to`, a range filter and the `assert_scoped` guard. With the filter OFF in the fixed system 19 of 36 cases fail.

### S6 — Week 8's trajectory eval is built on pre-extracted metadata
`data/w7_questions.json` gives each question its `target_name` up front. The integrated agent gets plain English, so it has to find the symbol itself.
Status: **fixed** — `w12_symbols.extract_symbols` finds names in plain English; 13 trajectory cases written for it. See S25 for the symbol-sweep gap it still has (T10).

### S7 — The old changelog says "deprecated in v3"; the brief needs "removed in 3.0"
`data/changelog.json` (Weeks 7–11) marks `Client.sendMessage` etc. as deprecated in v3 and says nothing about removal. "That method no longer exists in 3.0" would be a false sentence against that file.
Status: **accepted** — `data/changelog.json` is untouched (Weeks 7-11 outputs depend on it). `corpus/symbols.json` refines it, and `tests/test_w12.py` checks every old name is in the new table with `removed = 3.0`.

---

## Found while running (appended in order)

### S8 — A sample I tagged "2.0 to 2.4" calls a method that only exists from 2.2 (found by running the new code checker over my own corpus)
`corpus/samples/v2/headers_2_0.py` was labelled for 2.0–2.4 but calls `client.send()`, added in 2.2; a 2.1 caller who got it would hit `AttributeError`. This is the brief's "every sample cited to the version it compiles against" failing on the corpus itself, before any model was involved. A second one: the 2.0 polling sample read `.text` from an object type that only exists from 2.4.
Status: **fixed** — corrected; and the lint (guard G01) now runs every code block at every version in its range on every run, so it cannot come back unseen.

### S9 — The version resolver read a MENTION of a method as pasted CODE (found by running it)
"Does client.pollStream still work in 3.0?" was resolved as "caller is on 2.0, inferred from code". Nobody pasted code; they named a method. The symbol finder (written for the agent) and the resolver (written for the version) have different ideas of what "uses a symbol" means.
Status: **fixed** — `extract_symbols(usage_only=True)` is what the resolver uses: a symbol only tells you the version if it is CALLED.

### S10 — Week 3's own v3 docs contain code that does not run on its own (found by running the checker over every corpus code block)
`docs/responses.md` and `docs/streaming.md` (Week 3, the 3.0 reference) show example fragments that use `client` / `Client` without defining or importing them. They are fine as documentation and fail as "a sample that runs". If the agent trusted a retrieved docs example the way the Week 7 agent did, it would hand a caller code that raises `NameError`.
Status: **accepted** — Week 3's pages are not edited. The code gate rejects those fragments (they raise NameError) and the agent falls back to a sample; guard G01 lists them in `KNOWN_FRAGMENTS` rather than hiding them.

### S11 — Two of MY v2 doc sections said "valid 2.0–2.4" but their examples call `send()`, added in 2.2
Same class as S8, in the prose pages instead of the sample files. Found by the same lint (every block, every minor version in its range).
Status: **fixed** — the v2 requests, errors and changelog sections now carry the ranges they really have (G01 would catch a repeat).

### S12 — The Week 3-4 retriever has no stemmer, so "paginate" never finds "pagination" (found by running the first retrieval check)
The headline question of the brief returned the migration guide for a 2.4 caller. TF-IDF and BM25 treat paginate / pagination / paging as three unrelated words; "retry" and "retries" too (found later, by C15).
Status: **fixed** — `src/w12_text.py`: one small suffix stripper applied to the indexed text AND the query, never to what the caller sees. First attempt was query-side word variants gated on rarity; that moved the ranking of unrelated questions (C27) and the cut-off was fitted to one case, so it was thrown away.

### S13 — The Stack Overflow bridge hijacked a good question (found by running it)
"how do I stream a reply" matched the SO title "how do I read the status code from the reply object" (cosine 0.63 on one shared word) and appended `Response status_code` to the query.
Status: **fixed** — the bridge now fires only when the question uses words the DOCS never use ("hangs", "freezes"): a vocabulary gap. Even so, it earned nothing on 12 questions (so_ablation.md).

### S14 — Redaction and retrieval, each correct alone, broke case C31 together (found by a regression)
`[REDACTED:connection_string]` is a word the docs never use. The vocabulary-gap detector read it as a gap, the Stack Overflow bridge fired on it, and a pagination question got a `send()` sample.
Status: **fixed** — `strip_markers` removes the placeholders before a question is searched. The log still shows them.

### S15 — "paginate" is in no sample's code (found by C31 again)
The pagination sample says "Page through messages" and calls `list_messages`; its code never contains the word the user types.
Status: **fixed** — samples carry a `# tags:` header and the tags are indexed. This is a corpus-authoring change, and it helps this eval set; a real samples repo would need the same metadata.

### S16 — Three components had three different ideas of "the same word" (found while fixing S12-S15)
The index stemmed properly; the agent compared 4-letter prefixes; the composer compared 5-letter prefixes. "paginate" matched "pagination" in one place and not in the next.
Status: **fixed** — one `stem()` in `w12_text.py`, used by all three.

### S17 — Generic words count as evidence (found by the version sweep: a timeout sample offered to a headers question)
"request" appeared in a `print("the request timed out")` and in the send sample's tags, so a 2.1 caller asking for a header got a sample for something else.
Status: **fixed** — generic words ("request", "client", "message", "send" ...) count in a TITLE but never in a tag line or a body (`GENERIC`); this is the `relevance_floor` flag, and the closed loop in `closed_loop.md`.

### S18 — After saying a method is removed, the answer showed a sample that CALLS it (found by reading answer C18 by eye; no assertion caught it)
"Does client.pollStream still work in 3.0?" was answered correctly in words and then illustrated with a `pollStream` example.
Status: **fixed** — a question about a removed or deprecated name never gets a sample that uses it. This was found by reading, not by a test: every assertion passed.

### S19 — The planner swept lifecycle one name per lap (found by the first smoke run: 7-10 laps, 5.6K tokens per question)
Status: **fixed** — independent calls in one lap run in parallel, as a tool-calling model does (laps 7-10 -> about 4). Still the main cost and latency driver (tenx.md).

### S20 — A sample range was wrong for the VERSIONS between samples (the sweep, 2.0 and 2.1)
Nothing in 2.0-2.1 can take a request header, and the system had no way to say so except by emitting something else.
Status: **fixed** — a plain "I can't answer that" (C36). The hole was found by the sweep, not by any of my 35 cases.

### S21 — Week 5's confidence floor cannot be integrated (found by measuring it)
Week 3-6 refused below a TF-IDF cosine of 0.38. In this corpus the junk answer to C34 scores 0.43, higher than twelve correct answers; any single floor either over-refuses (Week 5's top failure) or lets junk through.
Status: **accepted** — C34 stays a documented XFAIL. A real fix needs a different signal (an answer-support check against the passage), not a threshold.

### S22 — The judge treated `list_messages` as one word, so it never matched "messages" (found by the judge saying N to answers I could see were fine: C03, C11, C31)
Status: **fixed** — and the agreement number is optimistic because of it (EVAL_REPORT.md says so).

### S23 — Running the old Week 9 tests rewrites three TRACKED log files (found by `git status` after running the baseline)
`output/w9/gateway_audit.log`, `output/w9/registry_access.log`, `third_party/package_registry/access.log` change every time `pytest` runs.
Status: **accepted** — not mine and out of scope. I restored them with `git checkout` after each baseline run so this branch does not carry test-run noise.

### S24 — A secret leaked to disk through the one place the Week 11 redactor did not reach (found by the canary cases, not predicted)
The engine redacted its own log on write. The MCP server, a separate process, logged the question it received under its own rules.
Status: **fixed** — one redactor (`w12_redact.py`) used by both processes and applied before the question leaves the engine. With only that flag on, planted-secret leaks go 3/3 -> 0/3.

### S25 — The symbol sweep checks the names it can SEE, not every name the code uses (found by the trajectory eval, T10)
The emitted code used `page=` (deprecated in 2.6, removed in 3.0); the agent looked up `per_page` but not `page`. The answer still passed because another notice happened to cover the same upgrade.
Status: **ran-out-of-time** — the fix is to sweep from the code checker's own symbol list instead of a regex over chunk text. Reported as the 0.154 outcome-vs-trajectory gap rather than hidden.

### S26 — The IDE says 2.4 and the pasted code needs 2.5 (case C07)
The engine believes the IDE. It notices `api_key` does not exist in 2.4 yet but never tells the caller that THEIR code cannot run on the version their IDE reports.
Status: **ran-out-of-time** — documented XFAIL; weakness 3.
