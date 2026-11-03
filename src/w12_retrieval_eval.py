"""Week 12: what do the Stack Overflow answers buy, and what do they cost?  (hostile question 3)

Three retrievers over the SAME 12 colloquial questions:

  A  scoped, Stack Overflow USED AS PHRASING ONLY        (the shipped design: SO is never returned, only its wording maps to a symbol)
  B  scoped, Stack Overflow DROPPED from the system       (bridge off -- the "just delete them" fix)
  C  Stack Overflow INDEXED AS ORDINARY DOCS, no version  (the lenient "search everything" first wiring)

Metrics: hit@3 (does a correct doc page appear in the top 3 for the caller's version?), and for C the POISON rate -- the
share of questions where a dead v1 Stack Overflow answer is in the top 3 (and in the top 1), i.e. a dead API the answer
could emit.
"""

import json
import os

import w12_index as ix
import w12_versions as V

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_cases():
    with open(os.path.join(BASE_DIR, "data", "w12", "retrieval_cases.json"), "r", encoding="utf-8") as fh:
        return json.load(fh)["cases"]


def _hit(results, pages):
    return any(r.chunk.page_id in pages and r.chunk.page_type != "stackoverflow" for r in results)


def run():
    idx = ix.get_index()
    rows = []
    for c in load_cases():
        v = V.parse(c["version"])
        v = (v[0], v[1] or 0)
        a, ia = idx.search(c["query"], v, top_k=3, page_types={"reference", "changelog"}, bridge=True)
        b, _ = idx.search(c["query"], v, top_k=3, page_types={"reference", "changelog"}, bridge=False)
        cc_, _ = idx.search(c["query"], None, top_k=3, mode="lenient", bridge=False)
        rows.append({"id": c["id"], "query": c["query"], "version": c["version"], "pages": c["pages"],
                     "A_hit": _hit(a, c["pages"]), "B_hit": _hit(b, c["pages"]), "C_hit": _hit(cc_, c["pages"]),
                     "A_bridge": (ia["so_bridge"] or {}).get("so_id"),
                     "C_so_in_top3": any(r.chunk.page_type == "stackoverflow" for r in cc_),
                     "C_so_top1": bool(cc_) and cc_[0].chunk.page_type == "stackoverflow",
                     "A_leaks_so": any(r.chunk.page_type == "stackoverflow" for r in a)})
    n = len(rows)
    s = {"n": n,
         "A_hit_at_3": sum(r["A_hit"] for r in rows) / n, "B_hit_at_3": sum(r["B_hit"] for r in rows) / n,
         "C_hit_at_3": sum(r["C_hit"] for r in rows) / n,
         "bridge_fired": sum(1 for r in rows if r["A_bridge"]),
         "C_so_in_top3": sum(r["C_so_in_top3"] for r in rows), "C_so_top1": sum(r["C_so_top1"] for r in rows),
         "A_so_leaks": sum(r["A_leaks_so"] for r in rows)}
    s["gained_by_so_bridge"] = round(s["A_hit_at_3"] - s["B_hit_at_3"], 4)
    return {"rows": rows, "summary": s}
