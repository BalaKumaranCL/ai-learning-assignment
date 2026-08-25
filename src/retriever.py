"""Local, no-API-key retrieval using TF-IDF + cosine similarity.

TF-IDF turns each chunk's text into a vector where rare, distinctive words
count for more than common ones. Cosine similarity then measures how close
two vectors point in the same direction, which works well as a "how
relevant is this chunk to this query" score without needing an embedding
model or network access.
"""

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from models import ScoredChunk


class TfidfRetriever:
    def __init__(self, chunks):
        if not chunks:
            raise ValueError("cannot build a retriever over zero chunks")

        self.chunks = list(chunks)
        self.vectorizer = TfidfVectorizer(stop_words="english")
        self.matrix = self.vectorizer.fit_transform(c.text for c in self.chunks)

    def search(self, query, top_k=5, sdk_version=None):
        """Return the top_k chunks for query, as a list of ScoredChunk.

        If sdk_version is given, only chunks whose sdk_version matches are
        considered at all -- filtering narrows the candidate pool BEFORE
        ranking, which is what lets filtering change the top-1 result
        instead of just re-labeling the same ranked list.
        """

        candidate_indices = list(range(len(self.chunks)))
        if sdk_version is not None:
            candidate_indices = [
                i for i in candidate_indices if self.chunks[i].sdk_version == sdk_version
            ]

        if not candidate_indices:
            return []

        query_vector = self.vectorizer.transform([query])
        candidate_matrix = self.matrix[candidate_indices]
        scores = cosine_similarity(query_vector, candidate_matrix)[0]

        ranked = sorted(
            zip(candidate_indices, scores), key=lambda pair: pair[1], reverse=True
        )

        results = []
        for rank, (chunk_index, score) in enumerate(ranked[:top_k], start=1):
            results.append(
                ScoredChunk(rank=rank, score=float(score), chunk=self.chunks[chunk_index])
            )
        return results
