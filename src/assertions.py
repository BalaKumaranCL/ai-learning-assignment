"""Deterministic, code-based checks -- criteria that never need a judge's
opinion because a parser or a metadata lookup settles them for free and
never has an off day.

Three assertions, each returning (passed: bool, detail: str):

1. no_unflagged_version_mismatch -- the cited chunk's sdk_version must match
   the question's requested sdk_version_filter (when one was given). This is
   this project's concrete version of "no symbol from the deprecations list
   appears without a migration note": legacy v2 content IS the deprecated
   list here, and citing it for a v3-scoped question with no migration note
   is exactly the DevRel "outdated code" risk.
2. code_sample_parses -- any ```python fenced block in the answer must be
   valid Python (ast.parse). Catches a chunk boundary slicing a code
   example in half, Week 3's original SimpleChunker failure mode.
3. cited_chunk_exists -- the chunk_id the answer claims to cite must
   actually exist in the current corpus. Catches a stale/invalid citation.
"""

import ast
import re

CODE_FENCE_RE = re.compile(r"```(?:python)?\n(.*?)```", re.DOTALL)


def no_unflagged_version_mismatch(case, chunk_by_id):
    """Catches two distinct real bugs, found by actually running this
    assertion against real cases rather than trusting it on paper:

    1. An explicit filter was requested, but the citation doesn't match it
       (the narrow check this assertion started as).
    2. NO filter was requested at all, and the citation is v2 anyway. This
       is the more dangerous case -- it's exactly how a caller (like the
       Slack integration in this project's traces) that never applies a
       filter ends up serving legacy content by default. An earlier version
       of this assertion skipped checking entirely when no filter was
       given, which meant it silently passed on the two clearest
       wrong-version regression cases in this eval set (E21, E22) --
       the opposite of what a deterministic safety check is for.
    """

    if case["cited_chunk_id"] is None:
        return True, "no citation -- nothing to check"

    chunk = chunk_by_id.get(case["cited_chunk_id"])
    if chunk is None:
        return False, f"cited chunk_id {case['cited_chunk_id']!r} does not exist in the corpus"

    if case["sdk_version_filter"] is not None:
        if chunk.sdk_version != case["sdk_version_filter"]:
            return False, (
                f"cited chunk is sdk_version={chunk.sdk_version!r} but the question requested "
                f"sdk_version_filter={case['sdk_version_filter']!r}"
            )
        return True, f"cited chunk sdk_version matches requested filter ({chunk.sdk_version!r})"

    if chunk.sdk_version == "v2":
        return False, (
            "no sdk_version_filter was requested at all, and the cited chunk is v2 -- "
            "legacy content should never be the unrequested default"
        )
    return True, "no filter was requested, and the cited chunk isn't v2"


def code_sample_parses(case, chunk_by_id):
    matches = CODE_FENCE_RE.findall(case["answer"])
    if not matches:
        return True, "no code fence in this answer"

    for code in matches:
        try:
            ast.parse(code)
        except SyntaxError as e:
            return False, f"code fence does not parse as valid Python: {e}"
    return True, f"{len(matches)} code fence(s), all parse as valid Python"


def cited_chunk_exists(case, chunk_by_id):
    if case["cited_chunk_id"] is None:
        return True, "no citation to check"
    if case["cited_chunk_id"] not in chunk_by_id:
        return False, f"cited chunk_id {case['cited_chunk_id']!r} does not exist in the corpus"
    return True, "cited chunk_id exists in the corpus"


ASSERTIONS = [
    ("no_unflagged_version_mismatch", no_unflagged_version_mismatch),
    ("code_sample_parses", code_sample_parses),
    ("cited_chunk_exists", cited_chunk_exists),
]


def run_assertions(case, chunk_by_id):
    """Run every assertion against one eval case. Returns a list of
    {name, passed, detail} dicts."""

    results = []
    for name, fn in ASSERTIONS:
        passed, detail = fn(case, chunk_by_id)
        results.append({"name": name, "passed": passed, "detail": detail})
    return results
