# Week 3 Practical — Task Set E (practice implementation)

This is a self-contained practice implementation of the "ingest the new SDK
reference pages and prove your chunking finds the answer" assignment. It
does not use the real assignment's six pages or the real Week 3 project
(neither was available) — instead it builds a small fictional "Acme SDK
v3" reference doc set from scratch and runs the full experiment against it,
so the numbers in [output/results.md](output/results.md) are real, computed
results, not invented ones.

## 1. What is chunking?

A RAG (Retrieval-Augmented Generation) app can't hand an entire
documentation site to a search engine or a language model at once. Instead,
each page gets cut into smaller pieces called **chunks**. Chunking is just
the process of deciding where those cuts go.

## 2. Why does chunking matter for RAG?

Where you cut matters as much as that you cut. If a cut lands in the middle
of a parameter table, one chunk might have the parameter's name and another
chunk might have its default value — and a search for "what is the default
of X" can miss both, because neither chunk has the whole answer. Bad
cutting points literally hide correct answers that are sitting right there
in the docs.

## 3. What is the current chunker?

See [src/chunkers.py](src/chunkers.py) → `SimpleChunker`. It is a
deliberately dumb baseline: it slices the raw page text into fixed-size
windows (400 characters, with 60 characters of overlap between consecutive
windows) with zero understanding of markdown. It doesn't know what a
header, a table, or a code fence is, so it can and does cut all three in
half.

## 4. What is the structure-aware chunker?

See [src/chunkers.py](src/chunkers.py) → `StructureAwareChunker`. It reads
the markdown structure: it only ever starts a new chunk at a `##` or `###`
heading, and it tracks whether it is currently inside a fenced code block
(` ``` `) so a `#` inside example Python code is never mistaken for a
heading. Because it only cuts at header boundaries, a parameter table
(header row + data rows) can never end up split across two chunks, and
neither can a code example.

## 5. What is metadata?

Every chunk carries `source_file`, `page_id`, `sdk_version`, and
`page_type`, plus an `anchor` (a breadcrumb like `Client > Client.send() >
Parameters`). Metadata is what lets you trace a chunk back to exactly where
it came from, and it's what makes filtering possible (see below). A chunk
with no `source_file` is treated as a failed ingest — see
`validate_chunks()` in [src/models.py](src/models.py).

## 6. What is top-5 retrieval?

For a given question, the retriever ranks every chunk by how similar it is
to the question (using TF-IDF + cosine similarity — see below) and returns
the 5 highest-scoring chunks. "Top-5" is just "did the right answer make it
into the 5 best guesses," which is a realistic bar: a real RAG app usually
only feeds the top handful of chunks to the answering step, not the whole
corpus.

**Cosine similarity**, briefly: TF-IDF turns a chunk's text into a vector of
numbers, one per word, where rare/distinctive words get bigger numbers than
common ones. Cosine similarity measures the angle between two such vectors
— a small angle (high score, close to 1) means the question and the chunk
use very similar, distinctive words; a large angle (low score, close to 0)
means they don't overlap much. No API key or embedding model is needed for
this — it's all local math via scikit-learn.

## 7. What does X/8 mean?

There are 8 questions whose answers are known in advance (see
[data/questions.json](data/questions.json)), written by reading the six
pages *before* ever running a search. For each chunking strategy, we run
all 8 questions and count how many of them have their known-correct chunk
show up in the top-5 results. "5/8" means 5 out of 8 questions succeeded
for that strategy. Running the *same* 8 questions against both strategies
is what makes the two numbers comparable — see
[output/results.md](output/results.md) section 4 for the real numbers and
the full per-question evidence behind them.

## 8. What is metadata filtering?

Sometimes the corpus has old and new documentation mixed together (in this
project, a couple of small *simulated* v2 chunks stand in for "legacy docs
that were already indexed" — see
[src/legacy_v2.py](src/legacy_v2.py)). A metadata filter narrows the search
to only chunks matching a value, e.g. `sdk_version=v3`, *before* ranking,
so an outdated v2 page can't outrank the current v3 answer just because it
happens to share more words with the query. Section 6 of
[output/results.md](output/results.md) shows this actually flipping the #1
result from a v2 chunk to a v3 chunk, with real scores.

## 9. Why should RAG refuse unsupported questions?

If a generator is told "use your best judgement" when the evidence is
weak, it will eventually produce a fluent, confident, completely made-up
answer — for example inventing a rate limit number that doesn't exist
anywhere in the docs. That's worse than no answer, because it looks
trustworthy. This project's generator
([src/generator.py](src/generator.py)) has a hard rule instead: if it can't
find text that actually supports the claim, it refuses, using a fixed
template ("I can't answer that from the supplied documentation because...")
rather than guessing.

## 10. How to run the project

```bash
# from the repo root
pip install -r requirements.txt

python run.py          # runs everything, writes output/results.md
pytest                 # runs the test suite (21 tests)
```

`run.py` prints a short summary (the two X/8 scores, whether the filter
demo flipped the top-1 result, how many answers were cited vs. refused) and
writes the full evidence to `output/results.md`, plus raw JSON dumps to
`output/chunks.json`, `output/search_dump.json`, `output/filter_demo.json`,
and `output/answers.json`.

## Project layout

```
ai-learning-assignment/        (repo root)
├── docs/               six fictional Acme SDK v3 reference pages
├── src/
│   ├── loader.py       reads docs/ into Page objects
│   ├── chunkers.py     SimpleChunker + StructureAwareChunker
│   ├── legacy_v2.py    two simulated v2 chunks, for the filter demo only
│   ├── models.py       Chunk/Page dataclasses + metadata validation
│   ├── retriever.py    TF-IDF + cosine similarity search, with filtering
│   ├── evaluator.py    runs the 8 questions, computes hit-in-top-5
│   ├── generator.py    grounded answers with citations, or refusal
│   ├── results_md.py   renders output/results.md from the run's data
│   └── pipeline.py     wires all of the above together
├── data/questions.json 8 known-answer + 3 unanswerable questions
├── output/             results.md and raw JSON evidence (generated)
├── tests/               21 pytest tests
└── run.py              entry point
```
