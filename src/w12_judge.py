"""Week 12: the answer JUDGE -- a heuristic stand-in for "an LLM judge" (same
convention as judge.py: this repo has no live model, so the judge is a
deterministic rule set whose rules are written down and whose agreement with a
human labeller is MEASURED, not assumed).

Criterion (single, binary): given only the question, the SDK version the IDE
sent (if any) and the answer text -- does this answer correctly and completely
tell THIS caller what they need, for THEIR version? A plain "that method no
longer exists" or "tell me your version" is Y when that is the right response.

It sees what a human labeller sees and nothing else: no expectations, no
trace, no retrieved chunks. Anything a parser can settle is NOT here -- that
is w12_assertions.py. The judge covers only what is left: is it relevant, is it
complete for the kind of question, is it internally consistent.

Rules (each one exists because of something a human would mark N):
  J1  asked-for-version  -> Y only if the question really carries no version evidence
  J2  refusal            -> N (like judge_v2: a refusal is "not helpful"; this IS a known weakness, see README)
  J3  version consistency-> the header version and every non-migration source must name the same major
  J4  relevance          -> the answer shares at least one content word with the question
  J5  how-to needs code  -> unless it says the method does not exist / no longer exists
  J6  status question    -> must say exists / no longer exists / deprecated
  J7  not a dump         -> prose over 1800 characters is N
"""

import re

_HEADER = re.compile(r"\*\*Answering for Acme SDK ([\d.]+)\*\*")
_SOURCE = re.compile(r"\]\(https?://[^)]*\)")
_STOP = {"stuck", "getting", "keeps", "returning", "tried", "trying", "please", "help", "error", "problem", "issue", "doing", "going",
         "what", "which", "when", "does", "this", "that", "with", "have", "from", "your", "about", "still", "work", "works",
         "there", "would", "could", "should", "where", "while", "they", "them", "then", "into", "like", "just", "also", "need", "want"}
_VERSION_EVIDENCE = re.compile(r"(?<![\w.])v?\d+\.\d+(?:\.\d+)?|\bv[23]\b|acme[-_]sdk\s*[=<>~]", re.I)


def _prose(answer):
    t = re.sub(r"```.*?```", "", answer, flags=re.DOTALL)
    t = t.split("**Sources:**")[0]
    return _HEADER.sub("", t)


def judge_w12(view):
    q, meta, ans = view["question"], view.get("sdk_version_sent"), view["answer"]

    if ans.startswith("I can't answer this safely yet"):                       # J1
        return "N" if (meta or _VERSION_EVIDENCE.search(q)) else "Y"
    if "I can't answer that from the Acme SDK" in ans:                          # J2
        return "N"

    m = _HEADER.search(ans)
    if m:                                                                       # J3
        major = m.group(1).split(".")[0]
        labels = re.findall(r"Acme SDK (\d+)\.(?:x|\d)\]?", ans.split("**Sources:**")[-1]) if "**Sources:**" in ans else []
        src_lines = [l for l in ans.split("**Sources:**")[-1].splitlines() if l.startswith("- [")] if "**Sources:**" in ans else []
        for line in src_lines:
            if "migration guide" in line or "changelog" in line:
                continue
            lab = re.search(r"Acme SDK (\d+)\.", line)
            if lab and lab.group(1) != major:
                return "N"

    prose = _prose(ans)
    q_clean = re.sub(r"\S*(://|@)\S*|sk_\w+|eyJ\S+|\w*\d\w*", " ", q)       # pasted secrets / urls / numbers are not the topic
    q_words = {w[:5] for w in re.findall(r"[a-z]{4,}", q_clean.lower()) if w not in _STOP}
    # relevance counts the CODE too: for a how-to question the sample IS the answer
    a_words = {w[:5] for w in re.findall(r"[a-z]{4,}", (ans.split("**Sources:**")[0]).lower())}
    if len(q_words) >= 2 and not (q_words & a_words):                           # J4
        return "N"

    has_code = "```python" in ans
    says_gone = re.search(r"does not exist|no longer exists", ans)
    if re.match(r"\s*(how (do|can|should|would) (i|we|you)|how to)\b", q, re.I) and not has_code and not says_gone:   # J5
        return "N"
    if re.search(r"\b(still work|still exist|exist|removed|deprecated)\b", q, re.I) and \
            not re.search(r"no longer exists|does not exist|still works|deprecat|exists", prose, re.I):          # J6
        return "N"
    if len(prose) > 1800:                                                       # J7
        return "N"
    return "Y"
