"""Runs the 8 known-answer questions against a retriever and scores hits.

A question "hits" for a strategy if one of its top-5 chunks both (a) comes
from the expected source file and (b) actually contains the expected answer
snippet. Checking the snippet -- not just the chunk_id -- matters because
the two chunkers slice the same page into different chunks, so there is no
single "correct chunk_id" that is comparable across strategies. Checking
against real page content also means we can't accidentally rig the result:
the snippet is written down before any retrieval ever runs.
"""


def evaluate_question(question, retriever, top_k=5):
    results = retriever.search(question["question"], top_k=top_k)

    hit = False
    hit_rank = None
    for scored in results:
        same_file = scored.chunk.source_file == question["expected_source_file"]
        has_snippet = question["expected_answer_snippet"] in scored.chunk.text
        if same_file and has_snippet:
            hit = True
            hit_rank = scored.rank
            break

    return {
        "id": question["id"],
        "question": question["question"],
        "expected_source_file": question["expected_source_file"],
        "expected_section": question["expected_section"],
        "expected_answer_snippet": question["expected_answer_snippet"],
        "hit": hit,
        "hit_rank": hit_rank,
        "top_5": [r.to_dict() for r in results],
    }


def evaluate_strategy(questions, retriever, top_k=5):
    per_question = [evaluate_question(q, retriever, top_k=top_k) for q in questions]
    score = sum(1 for r in per_question if r["hit"])
    return {"score": score, "total": len(questions), "per_question": per_question}


def locate_expected_chunk(question, retriever):
    """Search the FULL ranked chunk list (not just top-5) for the first
    chunk that actually contains the expected answer, so a miss can be
    diagnosed honestly: is the answer nowhere in the index at all (a real
    chunking/boundary problem), or does it exist but rank just below the
    top-5 cutoff (a ranking/dilution problem)? Returns None if the answer
    is not present in any chunk for this strategy at all.
    """

    results = retriever.search(question["question"], top_k=len(retriever.chunks))
    for r in results:
        same_file = r.chunk.source_file == question["expected_source_file"]
        has_snippet = question["expected_answer_snippet"] in r.chunk.text
        if same_file and has_snippet:
            return {
                "rank": r.rank,
                "score": r.score,
                "chunk_id": r.chunk.chunk_id,
                "anchor": r.chunk.anchor,
                "text": r.chunk.text,
            }
    return None
