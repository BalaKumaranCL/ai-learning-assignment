import json
import os

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _load_questions():
    with open(os.path.join(DATA_DIR, "questions.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)


def test_eight_answerable_questions_exist():
    questions = _load_questions()
    assert len(questions["answerable"]) == 8


def test_at_least_three_questions_depend_on_table_or_code_fence():
    questions = _load_questions()
    dependent = [
        q for q in questions["answerable"] if q["depends_on"] in ("parameter_table", "code_fence")
    ]
    assert len(dependent) >= 3


def test_every_question_has_a_known_location():
    questions = _load_questions()
    for q in questions["answerable"]:
        assert q["expected_source_file"]
        assert q["expected_section"]
        assert q["expected_answer_snippet"]


def test_three_unanswerable_questions_exist():
    questions = _load_questions()
    assert len(questions["unanswerable"]) == 3
