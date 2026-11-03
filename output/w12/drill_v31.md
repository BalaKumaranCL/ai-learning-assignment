# Drill: "we ship 3.1 next month with two more deprecations" (hostile question 4)

Simulated by editing **only the symbol table** (`corpus/symbols.json` copy, via `W12_MANIFEST`): `Client.close` -> `Client.shutdown` and `RequestOptions.query_params` -> `params`, both deprecated in 3.1. Docs, samples and changelog are NOT updated — the state of the world the morning the table changes and before the docs are re-cut.

- **Cases that go red: 1 of 38** — **G02**
  - G02: changelog_covers_table: 2 lifecycle entries in the symbol table but in no changelog: Client.close (deprecated 3.1), RequestOptions.query_params (deprecated 3.1)

- **Question-and-answer cases that go red: 0.** No sample or answer in the corpus uses `Client.close` or `query_params`, so a suite made only of questions would have stayed green and been *wrong* (the docs now call something current that the table calls deprecated). That is exactly the hostile question's point, and the reason guard **G02** exists: it compares the symbol table with the changelog pages directly.
- **Re-index cost:** rebuilding both version indexes + the Stack Overflow index takes **49 ms** here (137 chunks, 4,663 words). If the retriever used hosted embeddings instead of TF-IDF, that is about 6,062 tokens to embed (~$0.00012 at the assumed $0.00002/1K). Cheap either way; the cost of a docs release is the **review** of G01/G02, not the index.
- What I did NOT simulate: a real 3.1 docs page, a real sample using the new names, or a 3.1 caller in the suite (the 3.1 minor is accepted by the resolver and the filters but no case asks as a 3.1 caller).
