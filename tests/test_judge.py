import json
import os

from judge import judge_v1, judge_v2

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _eval_cases():
    with open(os.path.join(BASE_DIR, "data", "eval_set.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _labels():
    with open(os.path.join(BASE_DIR, "labels_25.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    return {l["id"]: l["label"] for l in data["labels"]}


def test_judge_v1_refuses_are_always_n():
    case = {"answered": False, "answer": "I can't answer that.", "question": "x", "sdk_version_filter": None}
    assert judge_v1(case) == "N"


def test_judge_v1_short_answered_text_is_n():
    case = {"answered": True, "answer": "# Streaming", "question": "x", "sdk_version_filter": None}
    assert judge_v1(case) == "N"


def test_judge_v1_substantial_answered_text_is_y():
    case = {"answered": True, "answer": "x" * 100, "question": "x", "sdk_version_filter": None}
    assert judge_v1(case) == "Y"


def test_judge_v2_flags_version_mismatch_when_filter_is_explicit():
    case = {
        "answered": True, "answer": "x" * 100, "question": "x", "sdk_version_filter": "v3",
        "cited_chunk_sdk_version": "v2", "cited_chunk_anchor": "Client.send() (v2) > retry_backoff_ms",
    }
    assert judge_v2(case) == "N"


def test_judge_v2_flags_example_anchor_for_a_non_example_question():
    case = {
        "answered": True, "answer": "x" * 100, "question": "what does status_code mean",
        "sdk_version_filter": "v3", "cited_chunk_sdk_version": "v3",
        "cited_chunk_anchor": "Responses > Response object > Example",
    }
    assert judge_v2(case) == "N"


def test_judge_v2_allows_example_anchor_when_question_asks_for_example():
    case = {
        "answered": True, "answer": "x" * 100, "question": "what value is used in the code example",
        "sdk_version_filter": "v3", "cited_chunk_sdk_version": "v3",
        "cited_chunk_anchor": "Client > Client.send() > Example",
    }
    assert judge_v2(case) == "Y"


def test_agreement_before_matches_reported_number():
    cases = _eval_cases()
    labels = _labels()
    agree = sum(1 for c in cases if judge_v1(c) == labels[c["id"]])
    assert agree == 23
    assert len(cases) == 31


def test_agreement_after_matches_reported_number():
    cases = _eval_cases()
    labels = _labels()
    agree = sum(1 for c in cases if judge_v2(c) == labels[c["id"]])
    assert agree == 24
