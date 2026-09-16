"""Runs the 12-question golden set against a retriever and scores hit-rate@3.

Mirrors evaluator.py's shape, but a "hit" is keyed on the golden set's known
chunk_id instead of a source_file + snippet text scan, since every golden
question pins one exact correct chunk.
"""


def evaluate_question_by_chunk_id(question, retriever, top_k=3):
    results = retriever.search(question["question"], top_k=top_k)

    hit = False
    hit_rank = None
    for scored in results:
        if scored.chunk.chunk_id == question["chunk_id"]:
            hit = True
            hit_rank = scored.rank
            break

    return {
        "id": question["id"],
        "question": question["question"],
        "expected_chunk_id": question["chunk_id"],
        "hit": hit,
        "hit_rank": hit_rank,
        "top_3": [r.to_dict() for r in results],
    }


def evaluate_golden_set(questions, retriever, top_k=3):
    per_question = [evaluate_question_by_chunk_id(q, retriever, top_k=top_k) for q in questions]
    score = sum(1 for r in per_question if r["hit"])
    return {"score": score, "total": len(questions), "per_question": per_question}


def locate_expected_chunk_by_id(question, retriever):
    """Search the FULL ranked chunk list (not just top-3) for the golden
    question's known-correct chunk_id, so a miss can be diagnosed honestly:
    does the chunk exist at all under this retriever (a ranking problem), or
    is it genuinely absent (a data problem)? Returns None in the latter case.
    """

    results = retriever.search(question["question"], top_k=len(retriever.chunks))
    for r in results:
        if r.chunk.chunk_id == question["chunk_id"]:
            return {
                "rank": r.rank,
                "score": r.score,
                "chunk_id": r.chunk.chunk_id,
                "anchor": r.chunk.anchor,
                "text": r.chunk.text,
            }
    return None
