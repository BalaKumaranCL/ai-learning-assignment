"""Labels every golden-set question R / G / HIT / NOT_IN_CORPUS and compares
before/after the retrieval change.

This project's generator (generator.answer_question) never paraphrases or
synthesizes an answer -- it only ever echoes the retriever's own rank-1
chunk verbatim, or refuses. That means a classic "model misread good
context" failure can't happen here in the usual sense. So "G" is defined
concretely for this project as: the correct chunk WAS found within top-3
(hit-rate@3 succeeds), but it is not the retriever's actual rank-1 pick --
i.e. the one thing a top-1-only reader would actually cite is still wrong,
even though the right evidence was sitting right there. Because that is a
ranking problem in disguise (not a true generation-side problem), it is
still something a retrieval change can fix, and the before/after comparison
tracks that honestly instead of writing it off in advance.

"R" means the correct chunk was outside the top-3 entirely but still exists
somewhere in the corpus (found by w4_evaluator.locate_expected_chunk_by_id).
"NOT_IN_CORPUS" means it was not found anywhere at all in the full ranked
list.
"""

from w4_evaluator import evaluate_question_by_chunk_id, locate_expected_chunk_by_id

LABELS = ("HIT", "R", "G", "NOT_IN_CORPUS")


def diagnose_question(question, retriever, top_k=3):
    eval_result = evaluate_question_by_chunk_id(question, retriever, top_k=top_k)

    if eval_result["hit"] and eval_result["hit_rank"] == 1:
        label = "HIT"
        evidence = f"correct chunk `{question['chunk_id']}` ranked #1 -- clean hit"

    elif eval_result["hit"]:
        label = "G"
        evidence = (
            f"correct chunk `{question['chunk_id']}` was in the top-3 at rank "
            f"#{eval_result['hit_rank']}, but a top-1-only reader would still cite "
            f"`{eval_result['top_3'][0]['chunk_id']}` instead"
        )

    else:
        location = locate_expected_chunk_by_id(question, retriever)
        if location is None:
            label = "NOT_IN_CORPUS"
            evidence = f"correct chunk `{question['chunk_id']}` not found anywhere in the full ranked list"
        else:
            label = "R"
            evidence = (
                f"correct chunk `{question['chunk_id']}` ranked #{location['rank']} "
                "-- outside the top-3 cutoff"
            )

    return {
        "id": question["id"],
        "question": question["question"],
        "expected_chunk_id": question["chunk_id"],
        "exact_token": question["exact_token"],
        "label": label,
        "evidence": evidence,
        "hit_rank": eval_result["hit_rank"],
    }


def tally_labels(diagnoses):
    tally = {label: 0 for label in LABELS}
    for d in diagnoses:
        tally[d["label"]] += 1
    return tally


def compare_before_after(baseline_diagnoses, questions_by_id, fused_retriever, top_k=3):
    """For every non-HIT baseline question, re-check it under the fused
    retriever and report what actually changed -- not just FIXED/UNFIXED for
    R, but rank movement for G too, since in this project a G failure is a
    ranking problem the same retrieval change can also touch.
    """

    rows = []
    for d in baseline_diagnoses:
        if d["label"] == "HIT":
            continue

        question = questions_by_id[d["id"]]
        fused_eval = evaluate_question_by_chunk_id(question, fused_retriever, top_k=top_k)
        fused_rank = fused_eval["hit_rank"]

        if d["label"] in ("R", "NOT_IN_CORPUS"):
            if fused_eval["hit"]:
                verdict = "FIXED"
            else:
                verdict = "UNFIXED"
        else:  # G
            if fused_rank == 1:
                verdict = "FIXED"
            elif not fused_eval["hit"]:
                verdict = "REGRESSED"
            elif fused_rank < d["hit_rank"]:
                verdict = "IMPROVED"
            elif fused_rank > d["hit_rank"]:
                verdict = "WORSENED"
            else:
                verdict = "UNCHANGED"

        rows.append(
            {
                "id": d["id"],
                "question": d["question"],
                "baseline_label": d["label"],
                "baseline_rank": d["hit_rank"],
                "fused_rank": fused_rank,
                "verdict": verdict,
            }
        )
    return rows
