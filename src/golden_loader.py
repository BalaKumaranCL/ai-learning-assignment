"""Loads and validates the Week 4 golden set (data/golden_set.jsonl).

Unlike Week 3's questions.json (matched by source_file + snippet), each
golden-set row pins one exact known-correct chunk_id, so a "hit" can be
checked with a simple equality instead of a text-containment scan.
"""

import json

REQUIRED_FIELDS = ("id", "question", "chunk_id", "source_file", "exact_token")


def load_golden_set(path):
    """Read a JSON Lines file into a list of question dicts, in file order."""

    questions = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            questions.append(json.loads(line))
    return questions


def validate_golden_set(questions):
    """Verify the golden set has the shape the assignment requires.

    Returns a list of error strings. An empty list means validation passed.
    """

    errors = []

    for q in questions:
        for field_name in REQUIRED_FIELDS:
            if not q.get(field_name) and q.get(field_name) is not False:
                errors.append(f"question id={q.get('id')!r} is missing required field {field_name!r}")

    if len(questions) != 12:
        errors.append(f"expected exactly 12 golden-set questions, found {len(questions)}")

    exact_token_count = sum(1 for q in questions if q.get("exact_token") is True)
    if exact_token_count < 4:
        errors.append(
            f"expected at least 4 questions with exact_token=true, found {exact_token_count}"
        )

    return errors
