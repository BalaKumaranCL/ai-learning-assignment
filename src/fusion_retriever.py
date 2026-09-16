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
