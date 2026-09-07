# Week 4 Practical — Task Set E (practice implementation)

This extends the Week 3 practice project (see [README-w3-task-e.md](README-w3-task-e.md)),
which already ships the structure-aware chunker + TF-IDF/cosine retriever as
its production system. This round asks a different question: even with
good chunking, does *retrieval ranking* still fail sometimes, and if so, can
one targeted change fix it? Like Week 3, this uses the same fictional "Acme
SDK v3" docs, so the numbers in [output/w4/results.md](output/w4/results.md)
are real, computed results.

## 1. What is hit-rate@3, and how is it different from Week 3's hit-in-top-5?

Same idea as Week 3's "hit in top-5," but stricter: for a given question,
does the single known-correct chunk appear anywhere in the retriever's
**top 3** results (not top 5)? A tighter cutoff is a harder bar to clear,
which is the point — it surfaces ranking problems that a looser top-5
cutoff would quietly hide.

## 2. What is BM25?

BM25 is, like the TF-IDF retriever Week 3 already built, a **keyword/lexical**
scoring method — it has no idea what any word *means*, only whether and how
often it appears. What it does differently is score term frequency with
**saturation** (a word appearing 10 times doesn't count 10x more than
appearing once) and **normalize for document length** (a short, focused
chunk isn't automatically penalized against a longer one). That can rank the
exact same set of chunks differently than plain TF-IDF cosine similarity
does, even over identical word overlap.

## 3. What is Reciprocal Rank Fusion (RRF), and why fuse ranks instead of scores?

TF-IDF cosine similarity and BM25 scores live on completely different,
incomparable scales — adding or averaging them would be meaningless, like
averaging a temperature in Celsius with one in Fahrenheit and calling it
useful. RRF sidesteps this entirely by ignoring the raw scores and only
looking at **rank position**: for each chunk, sum `1 / (k + rank)` across
every ranked list it appears in (here, `k = 60`, and there are two lists —
TF-IDF and BM25), then re-sort by that summed value. A chunk that ranks well
in *either* list gets a real boost; a chunk that ranks well in *both* gets
the strongest one.

## 4. Why did this project's failures NOT look like the assignment's scenario?

The assignment's scenario assumes the *current* retriever is a "dense"
embedding-based one, which is supposed to be great at meaning but bad at
exact symbols. This project's current retriever is TF-IDF — already
lexical, already good at exact symbols, for the same reason BM25 is. So
questions that name a parameter literally (`retry_backoff_ms`, `token_refresh_ms`)
mostly still get found. The real failures here come from a different, more
mundane cause: **dilution** — a chunk that happens to share a lot of the
same words as the query (often the neighboring `Example` chunk, which
literally repeats the parameter name in code) can outrank the one chunk that
actually answers the question. That's an honest divergence from the
assignment's assumed failure mode, reported plainly rather than
papered over — see section 4 of [output/w4/results.md](output/w4/results.md).

## 5. What do R, G, and Not-in-Corpus mean in this specific project?

- **R (retrieval failure):** the correct chunk never appears in the top-3 at
  all, but it does exist somewhere else in the corpus.
- **Not-in-Corpus:** the correct chunk doesn't exist anywhere in the corpus
  at all (a real data gap, not a ranking problem). Empirically empty for
  this run's golden set — worth stating rather than silently omitting.
- **G (in this project specifically):** this project's generator
  ([src/generator.py](src/generator.py)) never paraphrases an answer — it
  only ever echoes the retriever's single rank-1 chunk verbatim, or refuses.
  So the classic "model misread good context" failure can't really happen
  here. Instead, **G** means: the correct chunk *was* inside the top-3 (a
  hit-rate@3 success), but it wasn't the retriever's actual rank-1 pick — so
  a system that only ever reads rank-1 would still cite the wrong chunk.
  Because that's really a ranking problem wearing a generation-problem
  costume, the before/after comparison checks whether the *same* retrieval
  fix can resolve it too, instead of writing it off as untouchable in
  advance — and empirically, it sometimes can (see section 7 of
  [output/w4/results.md](output/w4/results.md)).

## 6. How to run it

```bash
# from the repo root
pip install -r requirements.txt   # adds rank_bm25 to Week 3's dependencies

python run_w4.py                     # runs everything, writes output/w4/results.md
pytest tests/test_w4_*.py tests/test_bm25_retriever.py tests/test_fusion_retriever.py
pytest                               # full suite, Week 3 + Week 4 (40 tests)
```

`run_w4.py` prints a short console summary (baseline vs. fused hit-rate@3,
the R/G/Not-in-Corpus tally, how many R-failures got fixed, before/after p50
latency) and writes the full evidence to `output/w4/results.md`, plus raw
JSON dumps to `output/w4/baseline_eval.json`, `output/w4/fused_eval.json`,
`output/w4/diagnosis.json`, `output/w4/latency.json`, and
`output/w4/comparison.json`.

## Project layout (additions on top of Week 3)

```
ai-learning-assignment/
├── data/golden_set.jsonl      12 real-phrased questions, each with a known-correct chunk_id
├── src/
│   ├── golden_loader.py       parses + validates golden_set.jsonl
│   ├── bm25_retriever.py      BM25Retriever (rank_bm25), same .search() interface as TfidfRetriever
│   ├── fusion_retriever.py    RRFRetriever -- fuses TF-IDF + BM25 ranks (k=60)
│   ├── latency.py             p50 latency measurement
│   ├── w4_evaluator.py        hit-rate@3, keyed on chunk_id
│   ├── w4_diagnosis.py        R / G / HIT / Not-in-Corpus labeling + before/after comparison
│   ├── w4_results_md.py       renders output/w4/results.md
│   └── w4_pipeline.py         wires all of the above together
├── output/w4/                 results.md and raw JSON evidence (generated)
├── tests/test_w4_*.py, tests/test_bm25_retriever.py, tests/test_fusion_retriever.py
└── run_w4.py                  entry point
```

Everything from Week 3 (`docs/`, `src/chunkers.py`, `src/retriever.py`,
`src/evaluator.py`, `src/generator.py`, `src/pipeline.py`, `run.py`,
`data/questions.json`) is untouched and still runs exactly as it did before.
