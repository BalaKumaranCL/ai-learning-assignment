"""The "docs assistant" as actually shipped and running in production for
this exercise: RRFRetriever (Week 4) for ranking, generator.py's citation
format, but NOT generator.answer_question()'s refuse/answer decision.

Why not reuse generator.answer_question() directly: it compares the
retrieved chunk's raw score against MIN_SCORE_THRESHOLD (0.38), a constant
calibrated for TfidfRetriever's cosine scores (0-1 scale). RRFRetriever's
fused score is 1/(k+rank) summed across two ranked lists -- with k=60, any
chunk that ranks #1 in both lists scores ~0.0328 REGARDLESS of how good the
match actually is (a perfect match and a totally unrelated query can score
identically). Wiring generator.answer_question() straight to RRFRetriever
as shipped would refuse on essentially every query -- discovered while
building this week's trace generator, not something pre-decided. This
module instead makes the refuse/answer decision from the WINNING chunk's
underlying TF-IDF cosine score (still meaningful on the original 0-1 scale,
so MIN_SCORE_THRESHOLD still applies) while citing whichever chunk the
FUSED ranking actually put on top. The RRF-score/threshold mismatch itself
is a real, separate bug worth fixing -- noted, not fixed, this week.
"""

from generator import MIN_SCORE_THRESHOLD

VERSION = "verbatim_cite_or_refuse_v2_rrf_confidence"


def _confidence_score(fused_retriever, question, winner_chunk_id, sdk_version):
    tfidf_full = fused_retriever.tfidf.search(
        question, top_k=len(fused_retriever.chunks), sdk_version=sdk_version
    )
    for r in tfidf_full:
        if r.chunk.chunk_id == winner_chunk_id:
            return r.score
    return 0.0


def _refusal_text(question):
    return (
        "I can't answer that from the supplied documentation "
        f"because the corpus does not document {question.rstrip('?')}."
    )


def answer_question(question, fused_retriever, sdk_version=None):
    """Same output shape as generator.answer_question: {answered, answer,
    chunk_id, score}. `score` here is the TF-IDF confidence used for the
    refuse decision, not the raw RRF fusion score."""

    top1 = fused_retriever.search(question, top_k=1, sdk_version=sdk_version)
    if not top1:
        return {"answered": False, "answer": _refusal_text(question), "chunk_id": None, "score": 0.0}

    winner = top1[0].chunk
    confidence = _confidence_score(fused_retriever, question, winner.chunk_id, sdk_version)

    if confidence < MIN_SCORE_THRESHOLD:
        return {"answered": False, "answer": _refusal_text(question), "chunk_id": None, "score": confidence}

    return {"answered": True, "answer": winner.text.strip(), "chunk_id": winner.chunk_id, "score": confidence}
