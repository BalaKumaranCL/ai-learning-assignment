"""The docs-assistant answer judge -- a heuristic stand-in for "an LLM
judge nobody has ever checked against a human" (see judge_v1.txt /
judge_v2.txt at the repo root for the plain-English criteria each version
actually applies; this module is the executable form of those same rules).

Single binary criterion throughout: is this answer helpful? (Y/N)
"""


def judge_v1(case):
    """See judge_v1.txt. Deliberately shallow: only checks whether
    SOMETHING substantial came back, never whether it's actually correct."""

    if not case["answered"]:
        return "N"
    if len(case["answer"].strip()) > 40:
        return "Y"
    return "N"


def judge_v2(case):
    """See judge_v2.txt. v1's two rules, plus two more, each driven by one
    real disagreement (E21, E16) read during this week's iteration step."""

    if not case["answered"]:
        return "N"

    if (
        case["sdk_version_filter"] is not None
        and case.get("cited_chunk_sdk_version") is not None
        and case["cited_chunk_sdk_version"] != case["sdk_version_filter"]
    ):
        return "N"

    anchor = case.get("cited_chunk_anchor") or ""
    if anchor.split(">")[-1].strip() == "Example" and "example" not in case["question"].lower():
        return "N"

    if len(case["answer"].strip()) > 40:
        return "Y"
    return "N"


JUDGE_VERSIONS = {"v1": judge_v1, "v2": judge_v2}
