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
