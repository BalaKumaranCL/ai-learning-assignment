# Week 4 Practical — Task Set E

Extends the Week 3 Acme SDK practice project. The docs assistant already ships the structure-aware chunker + TF-IDF/cosine retriever (see [README-w3-task-e.md](../../README-w3-task-e.md)); this round measures where THAT retriever still fails on a fresh 12-question golden set, labels every failure, and tests exactly one retrieval change against it.

## 1. Golden set (12 questions)

| ID | Question | chunk_id | exact_token |
|---|---|---|---|
| G1 | What is the default token_refresh_ms for AuthConfig? | `authentication::structure::2` | True |
| G2 | When should I call close() on my client and what does it clean up? | `client::structure::4` | False |
| G3 | What is the default retry_backoff_ms if I don't set one on send()? | `client::structure::2` | True |
| G4 | What is the default max_retries value before send() gives up retrying? | `client::structure::2` | True |
| G5 | What exception fires if my API key is missing or wrong? | `errors::structure::1` | False |
| G6 | If I pass a malformed parameter, what does the SDK throw? | `errors::structure::1` | False |
| G7 | Can I safely retry a send() call twice without it running twice server-side? | `requests::structure::4` | False |
| G8 | Is body_encoding json or form by default in RequestOptions? | `requests::structure::2` | True |
| G9 | How big is each chunk yielded by stream() unless I override it? | `streaming::structure::2` | False |
| G10 | How do I know when a stream has finished sending chunks? | `streaming::structure::4` | False |
| G11 | If the response status code isn't 200 what does that mean for my request? | `responses::structure::4` | False |
| G12 | My API key got leaked, what steps do I take to rotate it? | `authentication::structure::4` | False |

4 of 12 questions hinge on an exact token (a parameter name or an exception class) named in the question itself -- the rest are conceptual/procedural questions phrased the way a developer would actually ask them, without quoting the docs' own wording, per the assignment's warning against writing a golden set engineered to make the retriever look good.

## 2. Baseline hit-rate@3

**10/12** — written down before any retrieval change was made.

### Per-question baseline results

#### G1 — What is the default token_refresh_ms for AuthConfig?

- Expected: `authentication::structure::2`
- Result: **HIT** (rank 2)

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `authentication::structure::1` | v3 | 0.3909 | authentication.md | Authentication > AuthConfig |
| 2 | `authentication::structure::2` | v3 | 0.2886 | authentication.md | Authentication > AuthConfig > Parameters |
| 3 | `authentication::structure::3` | v3 | 0.2211 | authentication.md | Authentication > AuthConfig > Example |

#### G2 — When should I call close() on my client and what does it clean up?

- Expected: `client::structure::4`
- Result: **HIT** (rank 1)

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `client::structure::4` | v3 | 0.4196 | client.md | Client > Client.close() |
| 2 | `streaming::structure::1` | v3 | 0.1694 | streaming.md | Streaming > Client.stream() |
| 3 | `authentication::structure::4` | v3 | 0.1124 | authentication.md | Authentication > Rotating keys |

#### G3 — What is the default retry_backoff_ms if I don't set one on send()?

- Expected: `client::structure::2`
- Result: **HIT** (rank 2)

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `client::structure::3` | v3 | 0.3282 | client.md | Client > Client.send() > Example |
| 2 | `client::structure::2` | v3 | 0.1741 | client.md | Client > Client.send() > Parameters |
| 3 | `errors::structure::3` | v3 | 0.1692 | errors.md | Errors > Handling AcmeError generically |

#### G4 — What is the default max_retries value before send() gives up retrying?

- Expected: `client::structure::2`
- Result: **HIT** (rank 2)

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `responses::structure::0` | v3 | 0.1661 | responses.md | Responses |
| 2 | `client::structure::2` | v3 | 0.1483 | client.md | Client > Client.send() > Parameters |
| 3 | `errors::structure::1` | v3 | 0.1135 | errors.md | Errors > Exception table |

#### G5 — What exception fires if my API key is missing or wrong?

- Expected: `errors::structure::1`
- Result: **HIT** (rank 1)

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `errors::structure::1` | v3 | 0.2349 | errors.md | Errors > Exception table |
| 2 | `authentication::structure::0` | v3 | 0.1736 | authentication.md | Authentication |
| 3 | `authentication::structure::4` | v3 | 0.1377 | authentication.md | Authentication > Rotating keys |

#### G6 — If I pass a malformed parameter, what does the SDK throw?

- Expected: `errors::structure::1`
- Result: **MISS**

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `requests::structure::0` | v3 | 0.1244 | requests.md | Requests |
| 2 | `authentication::structure::4` | v3 | 0.1224 | authentication.md | Authentication > Rotating keys |
| 3 | `errors::structure::0` | v3 | 0.1196 | errors.md | Errors |

#### G7 — Can I safely retry a send() call twice without it running twice server-side?

- Expected: `requests::structure::4`
- Result: **HIT** (rank 1)

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `requests::structure::4` | v3 | 0.2521 | requests.md | Requests > Idempotency |
| 2 | `errors::structure::1` | v3 | 0.1159 | errors.md | Errors > Exception table |
| 3 | `client::structure::2` | v3 | 0.1032 | client.md | Client > Client.send() > Parameters |

#### G8 — Is body_encoding json or form by default in RequestOptions?

- Expected: `requests::structure::2`
- Result: **HIT** (rank 2)

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `requests::structure::1` | v3 | 0.4341 | requests.md | Requests > RequestOptions |
| 2 | `requests::structure::2` | v3 | 0.3548 | requests.md | Requests > RequestOptions > Parameters |
| 3 | `requests::structure::3` | v3 | 0.3095 | requests.md | Requests > RequestOptions > Example |

#### G9 — How big is each chunk yielded by stream() unless I override it?

- Expected: `streaming::structure::2`
- Result: **MISS**

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `streaming::structure::4` | v3 | 0.4811 | streaming.md | Streaming > StreamChunk |
| 2 | `streaming::structure::3` | v3 | 0.3753 | streaming.md | Streaming > Client.stream() > Example |
| 3 | `streaming::structure::1` | v3 | 0.1075 | streaming.md | Streaming > Client.stream() |

#### G10 — How do I know when a stream has finished sending chunks?

- Expected: `streaming::structure::4`
- Result: **HIT** (rank 1)

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `streaming::structure::4` | v3 | 0.3433 | streaming.md | Streaming > StreamChunk |
| 2 | `streaming::structure::1` | v3 | 0.2769 | streaming.md | Streaming > Client.stream() |
| 3 | `streaming::structure::3` | v3 | 0.2301 | streaming.md | Streaming > Client.stream() > Example |

#### G11 — If the response status code isn't 200 what does that mean for my request?

- Expected: `responses::structure::4`
- Result: **HIT** (rank 3)

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `responses::structure::3` | v3 | 0.3285 | responses.md | Responses > Response object > Example |
| 2 | `responses::structure::0` | v3 | 0.2617 | responses.md | Responses |
| 3 | `responses::structure::4` | v3 | 0.2524 | responses.md | Responses > Checking for errors |

#### G12 — My API key got leaked, what steps do I take to rotate it?

- Expected: `authentication::structure::4`
- Result: **HIT** (rank 2)

| Rank | chunk_id | sdk_version | Score | Page | Anchor |
|---|---|---|---|---|---|
| 1 | `authentication::structure::0` | v3 | 0.2869 | authentication.md | Authentication |
| 2 | `authentication::structure::4` | v3 | 0.2277 | authentication.md | Authentication > Rotating keys |
| 3 | `client::structure::0` | v3 | 0.1888 | client.md | Client |

## 3. Failure tally (R / G / Not-in-Corpus)

This project's generator never paraphrases an answer — it only ever echoes the retriever's own rank-1 chunk verbatim, or refuses. So a classic "model misread good context" failure can't happen here in the usual sense. **G** is defined concretely for this project as: the correct chunk WAS inside the top-3 (a hit-rate@3 success), but it was not the retriever's actual rank-1 pick — the one chunk a top-1-only reader would actually cite is still the wrong one. Because that's a ranking problem in disguise rather than a true generation-side problem, the before/after comparison below tracks whether the SAME retrieval change can fix it too, instead of writing it off in advance.

| Label | Count |
|---|---:|
| HIT | 4 |
| R | 2 |
| G | 6 |
| NOT_IN_CORPUS | 0 |

### Evidence, one line per non-HIT question

- **G1** (G): correct chunk `authentication::structure::2` was in the top-3 at rank #2, but a top-1-only reader would still cite `authentication::structure::1` instead
- **G3** (G): correct chunk `client::structure::2` was in the top-3 at rank #2, but a top-1-only reader would still cite `client::structure::3` instead
- **G4** (G): correct chunk `client::structure::2` was in the top-3 at rank #2, but a top-1-only reader would still cite `responses::structure::0` instead
- **G6** (R): correct chunk `errors::structure::1` ranked #4 -- outside the top-3 cutoff
- **G8** (G): correct chunk `requests::structure::2` was in the top-3 at rank #2, but a top-1-only reader would still cite `requests::structure::1` instead
- **G9** (R): correct chunk `streaming::structure::2` ranked #29 -- outside the top-3 cutoff
- **G11** (G): correct chunk `responses::structure::4` was in the top-3 at rank #3, but a top-1-only reader would still cite `responses::structure::3` instead
- **G12** (G): correct chunk `authentication::structure::4` was in the top-3 at rank #2, but a top-1-only reader would still cite `authentication::structure::0` instead

## 4. Why BM25 + RRF fusion (k=60)

Of 12 questions, 2 were genuine R-failures (the correct chunk existed but never surfaced in the top-3 at all) and 6 were G-failures (the correct chunk was in the top-3 but not the system's actual top-1 pick). Both are retrieval-ranking problems, not vocabulary-mismatch problems — every miss and near-miss chunk was still findable somewhere in the corpus by keyword overlap, just outranked by a topically-adjacent chunk (often one sharing the exact same parameter name, e.g. the `Example` chunk out-scoring the `Parameters` chunk it belongs next to). BM25's term-frequency saturation and document-length normalization re-rank short, focused chunks differently than raw TF-IDF cosine does over the same term overlap, and Reciprocal Rank Fusion combines that signal with the existing TF-IDF ranking by RANK (never by summing raw scores, which live on incomparable scales) — directly targeting this dilution pattern without discarding the retriever Week 3 already validated. A cross-encoder rerank was not chosen: it would need a new heavy dependency (sentence-transformers + torch) and a multi-hundred-MB model download, breaking this project's local/no-API-key design.

## 5. After hit-rate@3 (BM25 + RRF fusion)

**11/12** — same 12 questions, same corpus, the only variable changed is the retriever.

| | Before | After |
|---|---:|---:|
| hit-rate@3 | 10/12 | 11/12 |

## 6. Latency (p50 per query)

| | Before (TF-IDF only) | After (BM25 + RRF fusion) |
|---|---:|---:|
| p50 latency | 1.334 ms | 1.544 ms |

The fused retriever always runs a full TF-IDF search AND a full BM25 search internally, then fuses both complete ranked lists — so it is structurally guaranteed to cost at least as much as the baseline alone, plus fusion overhead. That cost is stated here honestly rather than explained away.

## 7. Per-question fixed / unfixed / improved

| ID | Baseline label | Baseline rank | Fused rank | Verdict |
|---|---|---|---|---|
| G1 | G | 2 | 2 | UNCHANGED |
| G3 | G | 2 | 3 | WORSENED |
| G4 | G | 2 | 1 | FIXED |
| G6 | R | — | 3 | FIXED |
| G8 | G | 2 | 1 | FIXED |
| G9 | R | — | — | UNFIXED |
| G11 | G | 3 | 2 | IMPROVED |
| G12 | G | 2 | 2 | UNCHANGED |

Of the 2 original R-failures, BM25 + RRF fixed `G6` and left `G9` completely untouched. As a secondary effect beyond hit-rate@3 itself, it also promoted `G4`, `G8` from a buried top-3 hit to the system's actual rank-1 pick.

## 8. Shipping decision

**Ship BM25 + RRF fusion.** hit-rate@3 improved from 10/12 to 11/12, fixing 1 of 2 R-failures and promoting 2 G-failures to a clean rank-1, for a latency cost of 0.210 ms per query (p50 1.334 -> 1.544 ms). On a 12-question corpus at sub-millisecond scale, that cost is negligible next to the accuracy gain — this verdict should be re-checked against real corpus size and query volume before shipping to production.

## 9. Code diff

The one retrieval change, in full — a new BM25 retriever, a new RRF fusion retriever wrapping it alongside the existing (unmodified) `TfidfRetriever`, and one new dependency line. Nothing in `retriever.py`, `evaluator.py`, `generator.py`, or `pipeline.py` was touched.

### `src/bm25_retriever.py` (new file)

```python
"""Local, no-API-key lexical retrieval using BM25 (rank_bm25's BM25Okapi).

BM25 is, like TF-IDF, a keyword/lexical scoring method -- it does not
understand meaning, only term overlap -- but it scores term frequency with
saturation and normalizes for document length, which can rank a short,
focused chunk differently than plain TF-IDF cosine similarity does over the
same term overlap. It is not a fix for vocabulary mismatch (a query with no
words in common with the correct chunk); it is a complementary signal to
combine with TF-IDF via rank fusion, not a replacement for it.
"""

import re

from rank_bm25 import BM25Okapi

from models import ScoredChunk

TOKEN_RE = re.compile(r"[a-z0-9_]+")


def _tokenize(text):
    """Lowercase word/number/underscore tokens.

    Underscore is included on purpose so a symbol like retry_backoff_ms
    stays one token -- matching how sklearn's default TF-IDF tokenizer also
    keeps underscores intact, which is why exact-symbol queries can work at
    all under either retriever.
    """

    return TOKEN_RE.findall(text.lower())


class BM25Retriever:
    def __init__(self, chunks):
        if not chunks:
            raise ValueError("cannot build a retriever over zero chunks")

        self.chunks = list(chunks)
        self.tokenized_corpus = [_tokenize(c.text) for c in self.chunks]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

    def search(self, query, top_k=5, sdk_version=None):
        candidate_indices = list(range(len(self.chunks)))
        if sdk_version is not None:
            candidate_indices = [
                i for i in candidate_indices if self.chunks[i].sdk_version == sdk_version
            ]

        if not candidate_indices:
            return []

        scores = self.bm25.get_scores(_tokenize(query))

        ranked = sorted(
            ((i, scores[i]) for i in candidate_indices), key=lambda pair: pair[1], reverse=True
        )

        results = []
        for rank, (chunk_index, score) in enumerate(ranked[:top_k], start=1):
            results.append(
                ScoredChunk(rank=rank, score=float(score), chunk=self.chunks[chunk_index])
            )
        return results
```

### `src/fusion_retriever.py` (new file)

```python
"""Combines TF-IDF/cosine and BM25 rankings with Reciprocal Rank Fusion.

RRF fuses RANKS, never raw scores: TF-IDF cosine similarity and BM25 scores
live on different, incomparable scales, so adding or averaging them would be
meaningless. Instead, for each chunk, we sum 1/(k + rank) over every ranked
list it appears in, then re-sort by that summed value. A chunk that ranks
well in EITHER list gets a strong contribution; a chunk that ranks well in
BOTH gets the strongest.
"""

from bm25_retriever import BM25Retriever
from models import ScoredChunk
from retriever import TfidfRetriever

RRF_K = 60


class RRFRetriever:
    """Drop-in replacement for TfidfRetriever: same chunks in, same
    .search(query, top_k, sdk_version) interface out."""

    def __init__(self, chunks, k=RRF_K):
        self.chunks = list(chunks)
        self.tfidf = TfidfRetriever(self.chunks)
        self.bm25 = BM25Retriever(self.chunks)
        self.k = k

    def search(self, query, top_k=5, sdk_version=None):
        n = len(self.chunks)

        # Pull the FULL ranked list from each sub-retriever, not just top_k --
        # truncating early would silently drop a chunk's contribution from
        # whichever list ranks it outside top_k but the other list ranks it
        # highly, which is exactly the cross-signal recovery RRF exists for.
        tfidf_ranked = self.tfidf.search(query, top_k=n, sdk_version=sdk_version)
        bm25_ranked = self.bm25.search(query, top_k=n, sdk_version=sdk_version)

        rrf_scores = {}
        chunk_by_id = {}
        for ranked_list in (tfidf_ranked, bm25_ranked):
            for scored in ranked_list:
                chunk_id = scored.chunk.chunk_id
                rrf_scores[chunk_id] = rrf_scores.get(chunk_id, 0.0) + 1.0 / (self.k + scored.rank)
                chunk_by_id[chunk_id] = scored.chunk

        ordered = sorted(rrf_scores.items(), key=lambda pair: (-pair[1], pair[0]))

        results = []
        for rank, (chunk_id, score) in enumerate(ordered[:top_k], start=1):
            results.append(ScoredChunk(rank=rank, score=float(score), chunk=chunk_by_id[chunk_id]))
        return results
```

### `requirements.txt` (modified -- added one line: rank_bm25>=0.2.2)

```text
scikit-learn>=1.3
pytest>=7.0
rank_bm25>=0.2.2
```

