# Top 3 known weaknesses — written BEFORE the first integrated eval run

Dated 2026-11-02. Written after the first end-to-end smoke test (6 questions, both configurations) and **before** the 32-case suite, the taxonomy, the judge check or any number in `EVAL_REPORT.md` existed. Nobody asked for this list. The file's modification time is earlier than every file in `output/w12/runs/` and `output/w12/eval/` — check it.

What I expect to be wrong, ranked by how much it would hurt an integrator:

## 1. Colloquial questions will miss (retrieval recall)

Retrieval is TF-IDF + BM25 fused with RRF — no embeddings. It has no idea that "my call just freezes" means `timeout_ms`. The Stack Overflow bridge only switches on when the question uses a word the docs never use, and only maps to the one closest SO title. Questions with words that DO appear in the docs but mean something else ("returns", "call") will pull in the wrong chunk with confidence. I expect the weakest cases to be the ones phrased the way real integrators type, not the way the docs are written.
*How I'll know:* hit@3 on a set of colloquial questions, with and without the Stack Overflow bridge. *What would fix it:* a real embedding model, which this repo has never had.

## 2. The symbol table is the only ground truth — and I wrote it

Every "does this method exist in 2.4?" answer, every deprecation notice, every removal version, **and the code checker that decides whether a sample "runs"** read the same hand-written file (`corpus/symbols.json`). The stub SDK that samples are executed against is generated from it too. If I got a version number wrong there, the checker, the stub, the notices and the eval would all agree with each other and all be wrong. "Passes the check" means "agrees with my table", not "runs on the real package". There is no real package in this repo to test against.
*How I'll know:* I can't, from inside the repo. The corpus self-test (every sample must pass for every version in its range) only proves the corpus is consistent with the table. *What would fix it:* running the samples against the real `acme_sdk` wheels for 2.4, 2.9 and 3.0 in CI.

## 3. A version I am told is a version I believe

If the IDE sends `sdk_version=2.4` the engine treats it as fact (confidence "high") and does not cross-check it against the code the user pasted. A user with a stale metadata file, or a monorepo with two SDK versions, gets a confident answer for the wrong one. And when only the major version is known ("v2"), the engine picks the lowest minor — code that works on every 2.x, but dated: it will show the `sendMessage` era API to someone who is probably on 2.8.
*How I'll know:* a case where metadata and pasted code disagree, and a major-only case. *What would fix it:* a contradiction check (metadata says 2.4, code uses `api_key=`, which needs 2.5+) that asks instead of answering.
