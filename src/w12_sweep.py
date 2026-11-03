"""Week 12: the version sweep -- an exploration, not a hand-picked suite.

My 35 eval cases are mine, so they can only find what I thought to ask. The
sweep asks the same core questions at EVERY version the SDK has shipped
(2.0 ... 2.9 and 3.0) and applies the version assertions to every answer:
does it resolve that version, stay in scope, cite that version's pages, and
give code that really runs on that version?

Whatever fails here is a hole nobody wrote a case for. Each hole becomes a
permanent eval case (see add_sweep_cases in run_w12.py).
"""

import w12_assertions as A
import w12_codecheck as cc

QUESTIONS = [
    ("send", "How do I send a message?"),
    ("stream", "How do I stream a reply?"),
    ("paginate", "How do I paginate through my messages?"),
    ("auth", "How do I authenticate?"),
    ("headers", "How do I add a custom header to a request?"),
    ("timeout", "How do I handle a timeout?"),
]
VERSIONS = [f"2.{m}" for m in range(10)] + ["3.0"]
# what a v2.x or 3.0 answer is allowed to cite
ALLOWED = {"2": ["2.x", "3.0"], "3": ["3.0"]}
# valid code that is about the WRONG thing is still a wrong answer: the code must mention what the question asked about
TOPIC_MARK = {"send": ("send(", "sendMessage("), "stream": (".stream(", "pollStream("), "paginate": ("list_messages",),
              "auth": ("AuthConfig(", "api_key="), "headers": ("RequestOptions(",), "timeout": ("TimeoutError",)}


# (topic, version) pairs where the SDK genuinely cannot do the thing: RequestOptions can only be passed to send(), added in 2.2.
# The right outcome there is a plain "I can't answer that" with NO code, never code about something else.
UNSUPPORTED = {("headers", "2.0"), ("headers", "2.1")}


def sweep_requests():
    return [{"case_id": f"S-{topic}-{v}", "question": q, "sdk_version": v} for v in VERSIONS for topic, q in QUESTIONS]


def grade(results):
    """-> list of {case_id, version, topic, failures[]} for every request that failed an assertion."""
    bad, total = [], len(results)
    for r in results:
        _, topic, v = r["case_id"].split("-", 2)
        case = {"expect": {"resolved": v, "code": True, "citation_versions": ALLOWED[v.split(".")[0]]}}
        fails = []
        for name, fn in A.ASSERTIONS:
            if name in ("expected_content", "removed_stated_plainly", "no_invented_signature", "pii_canaries_absent"):
                continue
            applicable, passed, detail = fn(r, case, {"requests": "", "server": ""})
            if applicable and not passed:
                fails.append(f"{name}: {detail}")
        code = "\n".join(cc.extract_code_blocks(r["answer"]))
        if (topic, v) in UNSUPPORTED:
            fails = [f for f in fails if not f.startswith("answered_as_expected")]
            if code:
                fails.append("unsupported on this version, but the answer emitted code anyway")
        elif not any(m in code for m in TOPIC_MARK[topic]):
            fails.append(f"topical: the code does not use {TOPIC_MARK[topic]}")
        if fails:
            bad.append({"case_id": r["case_id"], "version": v, "topic": topic, "trace_id": r["trace_id"], "failures": fails,
                        "answer_head": r["answer"][:160].replace("\n", " ")})
    return bad, total
