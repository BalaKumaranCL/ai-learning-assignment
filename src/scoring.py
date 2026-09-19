"""Deterministic, code-based pass/fail -- no judge's opinion involved.
A question passes if every one of its expected_keywords (each one traceable
to a specific tool's output) appears in the final answer text."""


def score_answer(question_meta, result):
    if result["answer"] is None:
        return False
    answer = result["answer"].lower()
    return all(kw.lower() in answer for kw in question_meta["expected_keywords"])
