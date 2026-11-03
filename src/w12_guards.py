"""Week 12: guard cases that watch the thing that MOVES -- the docs, the changelog and the symbol table -- rather
than any one answer.

A question-and-answer suite only notices a docs change if some answer happens to use the changed name. The hostile
question is: "we ship v3.1 next month with two more deprecations; which of your cases goes red the morning the docs
change? If the answer is none, your suite isn't watching the thing that moves." So two cases need no question:

  G01  corpus_code_lint       every code block in the corpus runs, for every version in its range, and no SAMPLE teaches a
                              deprecated call inside its own range (docs sections that DOCUMENT a deprecated name are exempt)
  G02  changelog_covers_table every deprecation / removal in the symbol table is stated in a changelog page, so the symbol
                              table and the prose cannot drift apart silently

They run against the symbol table named by W12_MANIFEST (the v3.1 drill points it at an edited copy).
"""

import re

import w12_codecheck as cc
import w12_index as ix
import w12_symbols as sym
import w12_versions as V

# Week 3's own 3.0 pages contain example FRAGMENTS (seam S10): they are not runnable alone. Known, listed, not hidden.
KNOWN_FRAGMENTS = {"v3:responses::structure::3", "v3:streaming::structure::3"}


def _versions_in(chunk):
    lo, hi = V.parse_exact(chunk.valid_from), V.parse_exact(chunk.valid_to)
    top = int(sym.latest(lo[0]).split(".")[1])
    return [(lo[0], m) for m in range(lo[1], min(hi[1], top) + 1)]


def corpus_code_lint(chunks=None):
    chunks = chunks or ix.load_corpus()
    problems, n = [], 0
    for c in chunks:
        if c.page_type == "stackoverflow" or "```python" not in c.text or c.chunk_id in KNOWN_FRAGMENTS:
            continue
        for v in _versions_in(c):
            if c.page_type == "migration" and v != (3, 0):
                continue                              # migration snippets are written for the NEW api
            res = cc.check_markdown(c.text, V.fmt(v))
            n += 1
            if not res["ok"]:
                problems.append(f"{c.chunk_id} @ {V.fmt(v)}: {res['problems'][0]['detail']}")
            elif c.page_type == "sample" and res["warnings"]:
                w = res["warnings"][0]
                problems.append(f"{c.chunk_id} @ {V.fmt(v)}: the sample teaches {w['symbol']}, deprecated {w['deprecated']}")
    return (not problems), (f"{n} (block, version) pairs run clean" if not problems else f"{len(problems)} problem(s), e.g. {problems[0]}")


def changelog_covers_table(chunks=None):
    chunks = chunks or ix.load_corpus()
    logs = [c for c in chunks if c.page_type == "changelog"]
    missing = []
    for sid, rec in sym.manifest()[1].items():
        if rec.get("kind") not in ("method", "param", "class") or not (rec.get("deprecated") or rec.get("removed")):
            continue
        short = sid.split(".")[-1]
        want = "Deprecated" if rec.get("deprecated") else "Removed"
        if not any(re.search(rf"\b{re.escape(short)}\b", c.text) and re.search(want, c.text, re.I) for c in logs):
            missing.append(f"{sid} ({want.lower()} {rec.get('deprecated') or rec.get('removed')})")
    n = sum(1 for r in sym.manifest()[1].values() if r.get("deprecated") or r.get("removed"))
    return (not missing), (f"all {n} lifecycle entries in the symbol table are in a changelog" if not missing
                           else f"{len(missing)} lifecycle entr{'y' if len(missing) == 1 else 'ies'} in the symbol table but in no changelog: {', '.join(missing)}")


GUARDS = [("G01", "corpus_code_lint", corpus_code_lint), ("G02", "changelog_covers_table", changelog_covers_table)]
