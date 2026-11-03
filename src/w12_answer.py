"""Week 12: the ANSWER composer -- the stand-in for the answer-writing model
(see llm_sim.py for the repo-wide convention: no live LLM, a deterministic,
documented stand-in instead).

It only ever writes from evidence the agent actually gathered (retrieved
passages and tool results) and it follows five rules the brief grades:

  1. The FIRST line says which SDK version the answer is for and where that
     version came from -- the version was resolved before anything else.
  2. Deprecations and removal versions are surfaced UNASKED, for every symbol
     the answer touches (not only the one the user named).
  3. A removed method is called removed -- "no longer exists in 3.0" -- with the
     migration, never a plausible-looking signature.
  4. A name that no release ever had is called unknown -- also plainly -- and no
     code is written for it.
  5. Every source is a clickable link that names the SDK version its page
     belongs to.

`compose` is deterministic: same evidence in, same text out.
"""

import re

import w12_symbols as sym
from w12_text import GENERIC, stems, strip_parens
from w12_versions import fmt, parse

SOURCE_LABEL = {"metadata": "your IDE's request metadata", "request_metadata": "your IDE's request metadata",
                "pinned_in_text": "the version pinned in your question", "stated_in_text": "the version you stated",
                "inferred_from_code": "the code you pasted (it only works on that range)",
                "inferred_from_error": "the error message you pasted",
                "mentioned": "the version mentioned in your question", "target_only": "the version you asked about",
                "defaulted_latest": "a DEFAULT (no version was sent) - this may be wrong for you"}

_HEADING = re.compile(r"^\s*#{1,6}\s")
_COMMENT = re.compile(r"<!--.*?-->")
_FENCE = re.compile(r"```.*?```", re.DOTALL)


def _prose(text):
    """Chunk text -> plain paragraphs (no headings, comments, tables or code)."""
    t = _FENCE.sub("", _COMMENT.sub("", text))
    paras = []
    for block in re.split(r"\n\s*\n", t):
        lines = [l for l in block.splitlines() if l.strip() and not _HEADING.match(l) and not l.strip().startswith("|")]
        if lines:
            paras.append(" ".join(l.strip() for l in lines))
    return paras


def _table_rows(text):
    rows = [l.strip() for l in text.splitlines() if l.strip().startswith("|")]
    return rows


def _question_terms(question):
    stop = {"what", "which", "is", "the", "a", "an", "of", "for", "in", "to", "do", "does", "default", "value", "how", "my", "i", "on",
            "when", "are", "can", "use", "get", "with", "from", "that", "this", "and", "or", "me", "it"}
    return {w for w in re.findall(r"[a-z_]{3,}", question.lower()) if w not in stop}


def _stem(w):
    return w[:5]


def _stems(text, min_len=4):
    return {_stem(w) for w in re.findall(r"[a-z_]{%d,}" % min_len, text.lower())}


class Line:
    def __init__(self, chunk, text, score, kind):
        self.chunk, self.text, self.score, self.kind = chunk, text, score, kind


def _fmt_row(header, cells):
    h = [x.lower() for x in header]
    if h[:3] == ["name", "type", "default"] and len(cells) >= 3:
        req = cells[3] if len(cells) > 3 else ""
        return f"{cells[0]} ({cells[1]}): default {cells[2]}" + (", required" if req.lower() == "true" else "")
    if h and h[0] == "exception" and len(cells) >= 3:
        return f"{cells[0]} is raised when {cells[1]} (retryable: {cells[2]})"
    return "; ".join(f"{k}: {v}" for k, v in zip(header, cells))


def _factual_lines(question, chunks):
    """The table rows (failing that, sentences) that best answer the question, best first. A row scores by how many
    question terms it contains (5-letter stems), plus a bonus when its first cell -- the name -- is one of them."""
    terms = {_stem(t) for t in _question_terms(question) if len(t) > 3}
    out = []
    for c in chunks:
        rows = _table_rows(c["text"])
        header = [x.strip() for x in rows[0].strip("|").split("|")] if rows else []
        for r in rows[2:]:
            cells = [x.strip() for x in r.strip("|").split("|")]
            cells[0] = cells[0].strip("`")
            score = len(terms & _stems(r)) + (2 if _stem(cells[0].lower()) in terms else 0)                 + 2 * len(terms & _stems(re.sub(r"[(][^)]*[)]", " ", c["anchor"])))     # the table of the method the question NAMES
            if score >= 2:
                out.append(Line(c, _fmt_row(header, cells), score, "row"))
        for para in _prose(c["text"]):
            for sent in re.split(r"(?<=[.!?])\s+", para):
                score = len(terms & _stems(sent))
                if score >= 3:
                    out.append(Line(c, sent.strip().rstrip("."), score - 1, "sentence"))
    out.sort(key=lambda l: (-l.score, 0 if l.kind == "row" else 1))
    return out


def _lead(topic_terms, docs):
    """The passage whose first paragraph is actually ABOUT the question (None if none is). A title match counts double; a
    body match counts only for DISTINCTIVE words -- generic ones ("request", "client", "message") made an intro to
    RequestOptions the answer to a timeout question. One stray word is not evidence: it takes 2 points."""
    best, best_score = None, 0
    for d in docs:
        paras = _prose(d["text"])
        if not paras:
            continue
        score = 2 * len(topic_terms & stems(strip_parens(d["anchor"]))) + len((topic_terms - GENERIC) & stems(paras[0]))
        if score > best_score:
            best, best_score = d, score
    return best if best_score >= 2 else None


def citation(chunk):
    """chunk record (dict from the server) -> {label, url, version_label, chunk_id}"""
    tail = chunk["anchor"].split(" > ")[-1] if chunk.get("anchor") else chunk["page_id"]
    kind = {"sample": "sample", "migration": "migration guide", "changelog": "changelog"}.get(chunk["page_type"], "reference")
    return {"label": f"{tail} - {kind}, Acme SDK {chunk['version_label']}", "url": chunk["url"],
            "version_label": chunk["version_label"], "chunk_id": chunk["chunk_id"], "page_type": chunk["page_type"]}


def lifecycle_notices(version, records):
    """Unasked notices. `records` are lookup results ({symbol, status, deprecated, removed, replacement, ...}).
    -> list of strings (markdown)."""
    caller = parse(version)
    out = []
    own = {r["symbol"] for r in records if r.get("known") and (r["status"] == "deprecated" or (r["status"] == "current" and r.get("removed")))}
    for r in records:
        if not r.get("known"):
            continue
        name = _nice(r["symbol"])
        repl = _nice(r["replacement"]) if r.get("replacement") else None
        since = r.get("replacement_available_since")
        usable_now = since and caller and sym.parse_exact_version(since) <= (caller[0], caller[1] or 0)
        repl_txt = ""
        if repl:
            repl_txt = f" Use `{repl}` instead" + (f" (available since {since}" + ("; you can switch now)." if usable_now else f"; you are on {version}, so upgrade to {since} first).") if since else ".")
        for old in r.get("replaces", []):
            if old["symbol"] in own:
                continue
            dep, rem = sym.parse_exact_version(old.get("deprecated")), sym.parse_exact_version(old.get("removed"))
            c = (caller[0], caller[1] or 0) if caller else None
            if dep and rem and c and dep <= c < rem:
                out.append(f"**Deprecation notice:** `{_nice(old['symbol'])}` - the previous name of `{name}` - has been deprecated since "
                           f"{old['deprecated']} and will be removed in {old['removed']}. If your code or an old tutorial still uses it, switch to `{name}`.")
            elif dep and rem and c and c < dep:
                out.append(f"**Heads-up for your upgrade:** `{_nice(old['symbol'])}` - the previous name of `{name}` - is deprecated from "
                           f"{old['deprecated']} and removed in {old['removed']}.")
        if r["status"] == "deprecated":
            rem = f" and will be removed in {r['removed']}" if r.get("removed") else ""
            out.append(f"**Deprecation notice:** `{name}` has been deprecated since {r['deprecated']}{rem}.{repl_txt}")
        elif r["status"] == "current" and r.get("removed"):
            dep = f" (deprecated from {r['deprecated']})" if r.get("deprecated") else ""
            out.append(f"**Heads-up for your upgrade:** `{name}`{dep} is removed in {r['removed']}.{repl_txt}")
    return list(dict.fromkeys(out))[:4]     # a wall of notices stops being read


def _nice(sid):
    """'Client.sendMessage' -> 'Client.sendMessage'; 'AuthConfig.token' -> 'AuthConfig(token=...)'"""
    parts = sid.split(".")
    if len(parts) == 2 and parts[0] in ("AuthConfig", "RequestOptions"):
        return f"{parts[0]}({parts[1]}=...)"
    if len(parts) == 3:
        return f"{parts[0]}.{parts[1]}({parts[2]}=...)"
    return sid


def compose(ev):
    """ev: dict assembled by the agent. -> {answer, answered, citations, clarification}

    ev keys: question, resolution, scope (version str), target, intent, named (list of
    {id, status_kind}), exists (id -> existence-check result), lifecycle (id -> record),
    docs / samples / upgrade (lists of chunk records), chosen_sample (chunk or None),
    sample_rejected (list of {chunk_id, problems}), gate (bool)."""
    res = ev["resolution"]
    scope = ev["scope"]
    head_src = SOURCE_LABEL.get(res["source"], res["source"])
    if res["source"] == "defaulted_latest":
        head = f"**Answering for Acme SDK {scope}** - version taken from {head_src}."
    else:
        head = f"**Answering for Acme SDK {scope}** (version taken from {head_src})."
    if res["source"] == "none":
        return {"clarification": True, "answered": False, "citations": [], "answer":
                "I can't answer this safely yet: **I don't know which Acme SDK version you are on**, and 2.x and 3.0 have "
                "different APIs (code written for one fails at runtime on the other). Run `pip show acme-sdk` and tell me the "
                "version, or let your IDE send it. I would rather ask than hand you a snippet that imports fine and breaks in production."}

    if res["source"] not in ("defaulted_latest", "target_only") and scope.startswith("2.") and not res.get("minor_exact"):
        head += (f"\n\n_I only know you are on the {scope[0]}.x line, not which minor release, so everything below works on every "
                 f"{scope[0]}.x version I could check from {scope}. Tell me your exact version (`pip show acme-sdk`) and I will use the recommended API for it._")

    body, cites = [], []
    notices = []
    named = ev["named"]
    unknown = [n for n in named if (ev["exists"].get(n["id"]) or {}).get("status") == "unknown" or n["status_kind"] == "unknown"]
    check_v = ev.get("check_version") or scope

    # --- 4. a name no release ever had ---
    for n in unknown[:1]:
        ex = ev["exists"].get(n["id"]) or {}
        nearest = ex.get("nearest") or []
        shown = n["text"].replace("(", "").strip() or n["id"]
        body.append(f"`{shown}()` does not exist in Acme SDK {check_v} - and it does not exist in any other 2.x or 3.0 release either. "
                    "I have no record of it in the reference or the changelog, so I won't guess a signature for it.")
        if nearest:
            body.append("The closest real names are " + ", ".join(f"`{x}`" for x in nearest) + ".")

    # --- 3. a name that existed and was removed / is not available at the version asked about ---
    for n in named:
        ex = ev["exists"].get(n["id"]) or {}
        rec = ev["lifecycle"].get(n["id"]) or ex.get("record") or {}
        if ex.get("status") == "removed":
            name = _nice(n["id"])
            repl = rec.get("replacement")
            line = f"`{name}` **no longer exists in {check_v}** - it was deprecated in {rec.get('deprecated')} and removed in {rec.get('removed')}."
            if repl:
                since = rec.get("replacement_available_since")
                line += f" Migration: use `{_nice(repl)}`" + (f", which has existed since {since}, so you can switch before you upgrade." if since else ".")
            body.append(line)
            if ev.get("caller_status", {}).get(n["id"]) == "deprecated":
                body.append(f"On your version ({scope}) it still works, but it is deprecated.")
        elif ex.get("status") == "not_yet":
            body.append(f"`{_nice(n['id'])}` does not exist in {check_v} yet - it was added in {rec.get('introduced')}.")

    # --- the content: a verified sample, the migration text, the docs ---
    docs, samples, upgrade = ev["docs"], ev["samples"], ev["upgrade"]
    chosen = ev.get("chosen_sample")
    if ev["intent"] == "factual" and docs:
        lines = _factual_lines(ev["question"], docs)
        if lines:
            best = lines[0]
            facts = list(dict.fromkeys(l.text for l in lines if l.chunk is best.chunk and l.score >= best.score - 1))[:3]
            cites.append(citation(best.chunk))
            body.append(f"In Acme SDK {scope}: " + "; ".join(facts) + ".")
        else:
            lead = _lead(ev["topic_terms"], docs)
            if lead:
                body.append(_prose(lead["text"])[0])
                cites.append(citation(lead))
    else:
        if upgrade and (ev["intent"] in ("status", "migration") or any((ev["exists"].get(n["id"]) or {}).get("status") == "removed" for n in named)):
            best = next((u for u in upgrade if u["page_type"] == "migration"), upgrade[0])   # the migration guide beats a changelog line
            paras = _prose(best["text"])
            if paras:
                body.append(paras[0])
            cites.append(citation(best))
        lead = _lead(ev["topic_terms"], docs)
        if lead and not body:
            body.append(_prose(lead["text"])[0])
        if lead:
            cites.append(citation(lead))
        if chosen:
            code = re.search(r"```python\n.*?```", chosen["text"], re.DOTALL)
            if code:
                body.append(f"Here is a sample for Acme SDK {scope}:\n\n{code.group(0)}")
                cites.append(citation(chosen))
        elif ev.get("wants_code") and not unknown and body:
            why = "(every candidate failed the parse/symbol check)" if ev.get("sample_rejected") else "(nothing in its samples matches your question)"
            body.append(f"I could not find a code sample that I can verify against Acme SDK {scope} {why}, so I am not giving you one.")

    if not body:
        return {"clarification": False, "answered": False, "citations": [], "answer":
                f"{head}\n\nI can't answer that from the Acme SDK {scope} documentation: nothing in the {scope} reference, samples or "
                "changelog matches. I would rather say so than guess."}

    # --- 2. unasked lifecycle notices, for everything the answer touched ---
    # a name already stated as removed above does not need the same sentence twice
    stated_removed = {n["id"] for n in named if (ev["exists"].get(n["id"]) or {}).get("status") == "removed"}
    notices = lifecycle_notices(scope, [r for r in ev["lifecycle"].values() if r.get("symbol") not in stated_removed])
    notices.sort(key=lambda n: 0 if n.startswith("**Deprecation") else 1)     # what applies NOW before what applies on upgrade

    # one citation per distinct url, in order
    seen, uniq = set(), []
    for c in cites:
        if c["url"] not in seen:
            seen.add(c["url"])
            uniq.append(c)
    if not uniq and (docs or samples):
        uniq.append(citation((docs or samples)[0]))

    parts = [head, "\n\n".join(body)]
    if notices:
        parts.append("\n\n".join(notices))
    parts.append("**Sources:**\n" + "\n".join(f"- [{c['label']}]({c['url']})" for c in uniq))
    return {"clarification": False, "answered": True, "citations": uniq, "answer": "\n\n".join(parts)}
